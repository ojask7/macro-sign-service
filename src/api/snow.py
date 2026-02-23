"""
ServiceNow (SNOW) Integration API endpoints.

Provides synchronous macro signing that returns signed content directly to the
SNOW form without requiring the caller to poll for a job result.

Endpoints:
  POST /snow/sign   - Sign a macro and return signed content immediately
  POST /snow/verify - Verify a previously signed macro
  GET  /snow/certs  - List available certificates in the key store
"""

from __future__ import annotations

import base64
from typing import Optional

from cryptography import x509 as _x509
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import RBACPermission, get_current_user
from src.config.logging import get_logger
from src.models.database import get_db
from src.models.pydantic_schemas import SNOWSignResponse, SNOWVerifyResponse
from src.models.schemas import AuditLog
from src.utils.file_validator import FileValidationError, FileValidator

logger = get_logger(__name__)

router = APIRouter(prefix="/snow", tags=["ServiceNow Integration"])

# Default test-domain certificate name in the key store
SNOW_TEST_DOMAIN = "snow-test-domain"


@router.post(
    "/sign",
    response_model=SNOWSignResponse,
    status_code=status.HTTP_200_OK,
    summary="Sign Macro for ServiceNow (Synchronous)",
    description=(
        "Synchronously sign a VBA macro file using the specified key-store certificate "
        "and return the signed content directly to the ServiceNow form. "
        "No polling required — result is available immediately in the response."
    ),
)
async def snow_sign_macro(
    request: Request,
    file: UploadFile = File(..., description="Macro file to sign (.vba, .bas, .cls, .frm, .vbs)"),
    algorithm: str = Form("sha256", description="Hash algorithm: sha256 | sha384 | sha512"),
    domain: str = Form(
        SNOW_TEST_DOMAIN,
        description="Certificate name in the key store (default: snow-test-domain)",
    ),
    requester_id: Optional[str] = Form(
        None, description="ServiceNow sys_id of the requesting user (for audit)"
    ),
    table: Optional[str] = Form(
        None, description="ServiceNow table name (for audit trail)"
    ),
    current_user=Depends(RBACPermission("sign")),
    db: AsyncSession = Depends(get_db),
) -> SNOWSignResponse:
    """
    Sign a macro file synchronously for ServiceNow form integration.

    The response contains:
    - ``signed_content_b64``: base64-encoded original file (SNOW stores/displays this)
    - ``signature``: hex-encoded digital signature (SNOW stores for later verification)
    - ``certificate_pem``: public cert PEM (SNOW can use for client-side verification)
    - ``certificate_fingerprint``, ``certificate_subject``, ``algorithm``, ``signed_at``
    """
    content = await file.read()
    filename = file.filename or "unknown.vba"

    # Validate file extension, size, and dangerous patterns
    validator = FileValidator()
    try:
        validator.validate(filename, content)
    except FileValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    from src.core.certificate_store import CertificateStoreError, get_certificate_store
    from src.core.signing_engine import SigningEngine, SigningError

    try:
        cert_store = get_certificate_store()

        # Auto-provision the test-domain cert if it doesn't exist yet
        cert_info = await cert_store.get_or_create_certificate(
            domain,
            common_name="snow-test.macro-sign.local",
            organization="SNOW Test Domain",
            days_valid=365,
        )

        engine = SigningEngine(
            private_key_pem=cert_info.private_key_pem,
            certificate_pem=cert_info.certificate_pem,
        )
        result = engine.sign(content, algorithm=algorithm)

    except CertificateStoreError as e:
        logger.error(
            "SNOW signing failed: certificate unavailable",
            domain=domain,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Signing certificate '{domain}' is not available: {e}",
        )
    except SigningError as e:
        logger.error("SNOW signing operation failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Signing failed: {e}",
        )

    # Build audit trail
    audit_parts = [f"file={filename}", f"domain={domain}", f"algo={algorithm}"]
    if requester_id:
        audit_parts.append(f"requester={requester_id}")
    if table:
        audit_parts.append(f"table={table}")

    audit = AuditLog(
        action="snow.signing.completed",
        resource_type="snow_sign",
        user_id=current_user.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
        details=", ".join(audit_parts),
        status="success",
    )
    db.add(audit)
    await db.flush()

    logger.info(
        "SNOW macro signed successfully",
        filename=filename,
        domain=domain,
        algorithm=algorithm,
        user=current_user.username,
        requester_id=requester_id,
    )

    cert_obj = _x509.load_pem_x509_certificate(cert_info.certificate_pem)

    return SNOWSignResponse(
        status="signed",
        original_filename=filename,
        file_size=len(content),
        signed_content_b64=base64.b64encode(content).decode(),
        signature=result.signature.hex(),
        file_hash=result.file_hash,
        certificate_fingerprint=result.certificate_fingerprint,
        certificate_subject=cert_obj.subject.rfc4514_string(),
        certificate_pem=cert_info.certificate_pem.decode(),
        algorithm=result.algorithm,
        signed_at=result.signed_at,
        requester_id=requester_id,
        domain=domain,
    )


@router.post(
    "/verify",
    response_model=SNOWVerifyResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify SNOW Macro Signature",
    description=(
        "Verify the digital signature on a macro file previously signed via "
        "the SNOW signing endpoint. Returns validation result and certificate details."
    ),
)
async def snow_verify_macro(
    request: Request,
    file: UploadFile = File(..., description="The original macro file to verify"),
    signature: str = Form(..., description="Hex-encoded signature from the sign response"),
    algorithm: str = Form("sha256", description="Hash algorithm used during signing"),
    domain: str = Form(
        SNOW_TEST_DOMAIN,
        description="Certificate domain used when signing (default: snow-test-domain)",
    ),
    current_user=Depends(RBACPermission("verify")),
    db: AsyncSession = Depends(get_db),
) -> SNOWVerifyResponse:
    """Verify a SNOW-signed macro file against the key-store certificate."""
    content = await file.read()

    try:
        signature_bytes = bytes.fromhex(signature)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid signature format — must be hex-encoded.",
        )

    from src.core.certificate_store import CertificateStoreError, get_certificate_store
    from src.core.signing_engine import SigningEngine

    try:
        cert_store = get_certificate_store()
        cert_info = await cert_store.get_certificate(domain)
        engine = SigningEngine(certificate_pem=cert_info.certificate_pem)
        result = engine.verify(content, signature_bytes, algorithm=algorithm)
    except CertificateStoreError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Certificate '{domain}' not found: {e}",
        )
    except Exception as e:
        logger.error("SNOW verification error", error=str(e))
        return SNOWVerifyResponse(
            is_valid=False,
            message=f"Verification error: {e}",
            domain=domain,
        )

    # Audit log
    audit = AuditLog(
        action="snow.verification.completed",
        resource_type="snow_verify",
        user_id=current_user.id,
        ip_address=request.client.host if request.client else None,
        details=f"domain={domain}, result={'valid' if result.is_valid else 'invalid'}",
        status="success" if result.is_valid else "failure",
    )
    db.add(audit)
    await db.flush()

    return SNOWVerifyResponse(
        is_valid=result.is_valid,
        certificate_subject=result.certificate_subject,
        certificate_issuer=result.certificate_issuer,
        certificate_expiry=result.certificate_expiry,
        message=result.message,
        domain=domain,
    )


@router.get(
    "/certs",
    summary="List Key Store Certificates",
    description="List all certificate names available in the configured key store.",
)
async def snow_list_certs(
    current_user=Depends(RBACPermission("sign")),
) -> dict:
    """Return a list of certificate names available for SNOW signing."""
    from src.core.certificate_store import get_certificate_store

    cert_store = get_certificate_store()
    try:
        names = await cert_store.list_certificates()
        return {"certificates": names, "count": len(names)}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to list certificates: {e}",
        )
