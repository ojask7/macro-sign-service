"""
Signing API endpoints.
POST /sign - Submit a macro file for signing
GET /status/{job_id} - Check signing job status
POST /verify - Verify a signed macro
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import RBACPermission, get_current_user
from src.config.logging import get_logger
from src.models.database import get_db
from src.models.pydantic_schemas import (
    JobStatusEnum,
    SigningJobList,
    SigningJobResponse,
    VerifyResponse,
)
from src.models.schemas import AuditLog, SigningJob, SigningProfile, JobStatus
from src.utils.file_validator import FileValidationError, FileValidator
from src.utils.rate_limiter import rate_limit_middleware

logger = get_logger(__name__)

router = APIRouter(prefix="/sign", tags=["Signing"])


@router.post(
    "",
    response_model=SigningJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Sign a Macro File",
    description="Submit a VBA macro file for digital signing. Returns a job ID for tracking.",
    dependencies=[Depends(rate_limit_middleware)],
)
async def sign_macro(
    request: Request,
    file: UploadFile = File(..., description="The macro file to sign"),
    profile: Optional[str] = Form(None, description="Signing profile name"),
    algorithm: str = Form("sha256", description="Hash algorithm"),
    webhook_url: Optional[str] = Form(None, description="Webhook URL for completion"),
    current_user=Depends(RBACPermission("sign")),
    db: AsyncSession = Depends(get_db),
) -> SigningJobResponse:
    """Submit a macro file for signing."""
    # Read and validate the file
    content = await file.read()
    filename = file.filename or "unknown.vba"

    validator = FileValidator()
    try:
        validator.validate(filename, content)
    except FileValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    # Resolve signing profile
    profile_record = None
    if profile:
        result = await db.execute(
            select(SigningProfile).where(
                SigningProfile.name == profile,
                SigningProfile.is_active == True,
            )
        )
        profile_record = result.scalar_one_or_none()
        if not profile_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Signing profile '{profile}' not found",
            )

    # Create signing job record
    job_id = uuid.uuid4()
    job = SigningJob(
        id=job_id,
        status=JobStatus.QUEUED,
        original_filename=filename,
        file_size=len(content),
        algorithm=algorithm,
        user_id=current_user.id,
        profile_id=profile_record.id if profile_record else None,
        webhook_url=webhook_url,
    )
    db.add(job)

    # Create audit log
    audit = AuditLog(
        action="signing.requested",
        resource_type="signing_job",
        resource_id=str(job_id),
        user_id=current_user.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
        details=f"File: {filename}, Size: {len(content)} bytes, Algorithm: {algorithm}",
    )
    db.add(audit)
    await db.flush()

    # Queue the signing task
    try:
        from src.queue.tasks import sign_macro_task

        cert_name = profile_record.certificate_name if profile_record else "default"
        sign_macro_task.delay(
            job_id=str(job_id),
            file_content_hex=content.hex(),
            certificate_name=cert_name,
            algorithm=algorithm,
            webhook_url=webhook_url,
        )
    except Exception as e:
        logger.warning(
            "Failed to queue signing task, will process synchronously",
            error=str(e),
        )
        # Fall back to synchronous signing
        await _process_signing_sync(job, content, db)

    logger.info(
        "Signing job created",
        job_id=str(job_id),
        filename=filename,
        user=current_user.username,
    )

    return SigningJobResponse(
        job_id=str(job.id),
        status=JobStatusEnum(job.status.value),
        original_filename=job.original_filename,
        file_size=job.file_size,
        file_hash=job.file_hash,
        signature=job.signature,
        certificate_fingerprint=job.certificate_fingerprint,
        algorithm=job.algorithm,
        error_message=job.error_message,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


async def _process_signing_sync(
    job: SigningJob, content: bytes, db: AsyncSession
) -> None:
    """Fallback synchronous signing when Celery is unavailable."""
    from src.core.certificate_store import get_certificate_store
    from src.core.signing_engine import SigningEngine

    try:
        job.status = JobStatus.PROCESSING
        job.started_at = datetime.now(timezone.utc)

        cert_store = get_certificate_store()
        cert_info = await cert_store.get_certificate("default")

        engine = SigningEngine(
            private_key_pem=cert_info.private_key_pem,
            certificate_pem=cert_info.certificate_pem,
        )

        result = engine.sign(content, algorithm=job.algorithm)

        job.status = JobStatus.COMPLETED
        job.signature = result.signature.hex()
        job.file_hash = result.file_hash
        job.certificate_fingerprint = result.certificate_fingerprint
        job.completed_at = datetime.now(timezone.utc)

    except Exception as e:
        job.status = JobStatus.FAILED
        job.error_message = str(e)
        job.completed_at = datetime.now(timezone.utc)
        logger.error("Synchronous signing failed", error=str(e))

    await db.flush()


@router.get(
    "/jobs",
    response_model=SigningJobList,
    summary="List Signing Jobs",
    description="List signing jobs for the current user.",
)
async def list_signing_jobs(
    page: int = 1,
    per_page: int = 20,
    status_filter: Optional[str] = None,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SigningJobList:
    """List signing jobs with pagination."""
    query = select(SigningJob).where(SigningJob.user_id == current_user.id)

    if status_filter:
        try:
            job_status = JobStatus(status_filter)
            query = query.where(SigningJob.status == job_status)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status filter: {status_filter}",
            )

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    query = query.order_by(SigningJob.created_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    jobs = result.scalars().all()

    return SigningJobList(
        jobs=[
            SigningJobResponse(
                job_id=str(j.id),
                status=JobStatusEnum(j.status.value),
                original_filename=j.original_filename,
                file_size=j.file_size,
                file_hash=j.file_hash,
                signature=j.signature,
                certificate_fingerprint=j.certificate_fingerprint,
                algorithm=j.algorithm,
                error_message=j.error_message,
                created_at=j.created_at,
                started_at=j.started_at,
                completed_at=j.completed_at,
            )
            for j in jobs
        ],
        total=total,
        page=page,
        per_page=per_page,
    )


router_status = APIRouter(prefix="/status", tags=["Signing"])


@router_status.get(
    "/{job_id}",
    response_model=SigningJobResponse,
    summary="Check Signing Job Status",
    description="Check the status of a signing job by its ID.",
)
async def get_signing_status(
    job_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SigningJobResponse:
    """Check the status of a signing job."""
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid job ID format",
        )

    result = await db.execute(
        select(SigningJob).where(SigningJob.id == job_uuid)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Signing job '{job_id}' not found",
        )

    # Check access: users can only see their own jobs (unless admin)
    from src.models.schemas import UserRole

    if job.user_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view this job",
        )

    return SigningJobResponse(
        job_id=str(job.id),
        status=JobStatusEnum(job.status.value),
        original_filename=job.original_filename,
        file_size=job.file_size,
        file_hash=job.file_hash,
        signature=job.signature,
        certificate_fingerprint=job.certificate_fingerprint,
        algorithm=job.algorithm,
        error_message=job.error_message,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


router_verify = APIRouter(prefix="/verify", tags=["Verification"])


@router_verify.post(
    "",
    response_model=VerifyResponse,
    summary="Verify a Signed Macro",
    description="Verify the digital signature on a macro file.",
    dependencies=[Depends(rate_limit_middleware)],
)
async def verify_macro(
    request: Request,
    file: UploadFile = File(..., description="The macro file to verify"),
    signature: str = Form(..., description="Hex-encoded signature"),
    algorithm: str = Form("sha256", description="Hash algorithm used"),
    current_user=Depends(RBACPermission("verify")),
    db: AsyncSession = Depends(get_db),
) -> VerifyResponse:
    """Verify a signed macro file."""
    content = await file.read()

    try:
        signature_bytes = bytes.fromhex(signature)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid signature format. Must be hex-encoded.",
        )

    # Perform verification
    from src.core.certificate_store import get_certificate_store
    from src.core.signing_engine import SigningEngine

    try:
        cert_store = get_certificate_store()
        cert_info = await cert_store.get_certificate("default")

        engine = SigningEngine(certificate_pem=cert_info.certificate_pem)
        result = engine.verify(content, signature_bytes, algorithm=algorithm)

        # Audit log
        audit = AuditLog(
            action="signing.verified",
            resource_type="verification",
            user_id=current_user.id,
            ip_address=request.client.host if request.client else None,
            details=f"Result: {'valid' if result.is_valid else 'invalid'}",
            status="success" if result.is_valid else "failure",
        )
        db.add(audit)

        return VerifyResponse(
            is_valid=result.is_valid,
            certificate_subject=result.certificate_subject,
            certificate_issuer=result.certificate_issuer,
            certificate_expiry=result.certificate_expiry,
            message=result.message,
        )

    except Exception as e:
        logger.error("Verification failed", error=str(e))
        return VerifyResponse(
            is_valid=False,
            message=f"Verification error: {str(e)}",
        )
