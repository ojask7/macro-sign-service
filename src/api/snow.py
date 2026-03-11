"""
ServiceNow (SNOW) Integration API endpoints.

Provides synchronous macro signing that returns signed content directly to the
SNOW form without requiring the caller to poll for a job result.

For Office macro files (.xlsm, .docm, etc.), uses VBA project signing so
that the certificate is visible under Alt+F11 → Tools → Digital Signature.

Endpoints:
  POST /snow/sign       - Sign a macro and return signed content immediately
  POST /snow/sign-vba   - Sign an Office file with embedded VBA signature
  POST /snow/verify     - Verify a previously signed macro
  GET  /snow/certs      - List available certificates in the key store
  GET  /snow/certs/{n}  - Get certificate details (proof of signing capability)
  GET  /snow/certs/{n}/pfx - Download PFX for Windows-side signing
  GET  /snow/certs/{n}/proof - Get full certificate proof for audit
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Optional

from cryptography import x509 as _x509
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import RBACPermission, get_current_user
from src.config.logging import get_logger
from src.config.settings import get_settings
from src.models.database import get_db
from src.models.pydantic_schemas import (
    CertificateProofResponse,
    SNOWSignResponse,
    SNOWSignVBAResponse,
    SNOWVerifyResponse,
)
from src.models.schemas import AuditLog
from src.utils.file_validator import FileValidationError, FileValidator

logger = get_logger(__name__)

router = APIRouter(prefix="/snow", tags=["ServiceNow Integration"])

# Default test-domain certificate name in the key store
SNOW_TEST_DOMAIN = "snow-test-domain"

# Office macro file extensions that support embedded VBA signatures
VBA_SIGNABLE_EXTENSIONS = {".xlsm", ".xlsb", ".docm", ".pptm", ".xltm", ".dotm", ".potm"}


def _is_office_macro_file(filename: str) -> bool:
    """Check if the file is an Office macro format that can be VBA-signed."""
    return Path(filename).suffix.lower() in VBA_SIGNABLE_EXTENSIONS


@router.post(
    "/sign",
    response_model=SNOWSignResponse,
    status_code=status.HTTP_200_OK,
    summary="Sign Macro for ServiceNow (Synchronous)",
    description=(
        "Synchronously sign a VBA macro file using the specified key-store certificate "
        "and return the signed content directly to the ServiceNow form. "
        "For plain text macros (.vba, .bas), returns a detached signature. "
        "For Office files (.xlsm, .docm), automatically uses VBA project signing."
    ),
)
async def snow_sign_macro(
    request: Request,
    file: UploadFile = File(..., description="Macro file to sign"),
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
    "/sign-vba",
    response_model=SNOWSignVBAResponse,
    status_code=status.HTTP_200_OK,
    summary="Sign Office Macro with Embedded VBA Signature",
    description=(
        "Sign an Office macro file (.xlsm, .docm, .pptm, etc.) so that the "
        "digital signature is embedded in the VBA project. The certificate will "
        "be visible under Alt+F11 → Tools → Digital Signature in Excel/Word. "
        "Requires signtool.exe + Office SIP DLLs (local Windows or remote agent)."
    ),
)
async def snow_sign_vba(
    request: Request,
    file: UploadFile = File(..., description="Office macro file (.xlsm, .docm, .pptm, etc.)"),
    algorithm: str = Form("sha256", description="Hash algorithm: sha256 | sha384 | sha512"),
    domain: str = Form(
        SNOW_TEST_DOMAIN,
        description="Certificate name in the key store",
    ),
    requester_id: Optional[str] = Form(
        None, description="ServiceNow sys_id of the requesting user"
    ),
    table: Optional[str] = Form(
        None, description="ServiceNow table name (for audit)"
    ),
    current_user=Depends(RBACPermission("sign")),
    db: AsyncSession = Depends(get_db),
) -> SNOWSignVBAResponse:
    """
    Sign an Office file with embedded VBA project signature.

    The signed file is returned as base64 in ``signed_file_b64``.
    The certificate will be visible in the VBA editor Digital Signature dialog.
    """
    content = await file.read()
    filename = file.filename or "unknown.xlsm"

    # Validate
    validator = FileValidator()
    try:
        validator.validate(filename, content)
    except FileValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if not _is_office_macro_file(filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"VBA signing requires an Office macro file format "
                f"({', '.join(sorted(VBA_SIGNABLE_EXTENSIONS))}). "
                f"Got: {Path(filename).suffix.lower()}"
            ),
        )

    from src.core.certificate_store import CertificateStoreError, get_certificate_store
    from src.core.vba_signing import VBASigningEngine, VBASigningError, pem_to_pfx

    settings = get_settings()

    try:
        cert_store = get_certificate_store()
        cert_info = await cert_store.get_or_create_certificate(
            domain,
            common_name="snow-test.macro-sign.local",
            organization="SNOW Test Domain",
            days_valid=365,
        )

        pfx_password = settings.signing.pfx_password
        engine = VBASigningEngine(
            certificate_pem=cert_info.certificate_pem,
            private_key_pem=cert_info.private_key_pem,
            pfx_password=pfx_password,
            windows_agent_url=settings.signing.windows_agent_url,
        )
        result = engine.sign_file(content, filename, algorithm=algorithm)

    except CertificateStoreError as e:
        logger.error("VBA signing failed: certificate unavailable", domain=domain, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Signing certificate '{domain}' is not available: {e}",
        )
    except VBASigningError as e:
        logger.error("VBA signing operation failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"VBA signing failed: {e}",
        )

    # If signing produced a package-for-windows, include the PFX
    pfx_b64 = None
    if result.signing_method == "unsigned-requires-windows" and cert_info.private_key_pem:
        pfx_bytes = pem_to_pfx(
            cert_info.certificate_pem,
            cert_info.private_key_pem,
            pfx_password=pfx_password.encode() if pfx_password else b"",
        )
        pfx_b64 = base64.b64encode(pfx_bytes).decode()

    # Audit trail
    audit_parts = [
        f"file={filename}",
        f"domain={domain}",
        f"algo={algorithm}",
        f"method={result.signing_method}",
    ]
    if requester_id:
        audit_parts.append(f"requester={requester_id}")
    if table:
        audit_parts.append(f"table={table}")

    audit = AuditLog(
        action="snow.vba_signing.completed",
        resource_type="snow_sign_vba",
        user_id=current_user.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
        details=", ".join(audit_parts),
        status="success",
    )
    db.add(audit)
    await db.flush()

    signed_filename = _make_signed_filename(filename)

    logger.info(
        "SNOW VBA macro signed",
        filename=filename,
        domain=domain,
        algorithm=algorithm,
        signing_method=result.signing_method,
        user=current_user.username,
    )

    return SNOWSignVBAResponse(
        status="signed",
        original_filename=filename,
        signed_filename=signed_filename,
        file_size=len(result.signed_file_bytes),
        signed_file_b64=base64.b64encode(result.signed_file_bytes).decode(),
        certificate_fingerprint=result.certificate_fingerprint,
        certificate_subject=result.certificate_subject,
        certificate_pem=result.certificate_pem,
        algorithm=result.algorithm,
        signed_at=result.signed_at,
        signing_method=result.signing_method,
        pfx_b64=pfx_b64,
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


@router.get(
    "/certs/{name}",
    summary="Get Certificate Details",
    description="Get X.509 details for a named certificate in the key store.",
)
async def snow_get_cert_details(
    name: str,
    current_user=Depends(RBACPermission("sign")),
) -> dict:
    """Return X.509 metadata for a specific certificate (no private key exposed)."""
    from src.core.certificate_store import CertificateStoreError, get_certificate_store
    from src.core.vba_signing import get_certificate_details

    cert_store = get_certificate_store()
    try:
        cert_info = await cert_store.get_certificate(name)
    except CertificateStoreError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Certificate '{name}' not found: {e}",
        )

    details = get_certificate_details(cert_info.certificate_pem)
    details["name"] = name
    details["has_private_key"] = cert_info.private_key_pem is not None
    return details


@router.get(
    "/certs/{name}/proof",
    response_model=CertificateProofResponse,
    summary="Certificate Signing Proof",
    description=(
        "Get full certificate proof showing the signing certificate details, "
        "key usage, and code signing capability. Use this to verify that the "
        "service has a valid code-signing certificate."
    ),
)
async def snow_cert_proof(
    name: str,
    current_user=Depends(RBACPermission("sign")),
) -> CertificateProofResponse:
    """Return certificate proof with code-signing validation for audit."""
    from src.core.certificate_store import CertificateStoreError, get_certificate_store
    from src.core.vba_signing import get_certificate_details

    cert_store = get_certificate_store()
    try:
        cert_info = await cert_store.get_certificate(name)
    except CertificateStoreError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Certificate '{name}' not found: {e}",
        )

    details = get_certificate_details(cert_info.certificate_pem)

    return CertificateProofResponse(
        name=name,
        subject=details["subject"],
        issuer=details["issuer"],
        serial_number=details["serial_number"],
        not_valid_before=details["not_valid_before"],
        not_valid_after=details["not_valid_after"],
        fingerprint_sha256=details["fingerprint_sha256"],
        key_type=details["key_type"],
        is_code_signing=details["is_code_signing"],
        extensions=details["extensions"],
        certificate_pem=details["certificate_pem"],
        pfx_available=cert_info.private_key_pem is not None,
    )


@router.get(
    "/certs/{name}/pfx",
    summary="Download PFX Certificate",
    description=(
        "Download the signing certificate as a PFX/PKCS#12 file for use with "
        "Windows signing tools (signtool.exe, Set-AuthenticodeSignature). "
        "This allows signing on the Windows machine directly."
    ),
)
async def snow_download_pfx(
    name: str,
    current_user=Depends(RBACPermission("sign")),
) -> Response:
    """Download the certificate + private key as PFX for Windows signing."""
    from src.core.certificate_store import CertificateStoreError, get_certificate_store
    from src.core.vba_signing import pem_to_pfx

    settings = get_settings()
    cert_store = get_certificate_store()
    try:
        cert_info = await cert_store.get_certificate(name)
    except CertificateStoreError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Certificate '{name}' not found: {e}",
        )

    if not cert_info.private_key_pem:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Certificate '{name}' does not have a private key — cannot export PFX.",
        )

    pfx_password = settings.signing.pfx_password
    pfx_bytes = pem_to_pfx(
        cert_info.certificate_pem,
        cert_info.private_key_pem,
        pfx_password=pfx_password.encode() if pfx_password else b"",
        friendly_name=name,
    )

    logger.info("PFX certificate downloaded", name=name, user=current_user.username)

    return Response(
        content=pfx_bytes,
        media_type="application/x-pkcs12",
        headers={
            "Content-Disposition": f'attachment; filename="{name}.pfx"',
        },
    )


def _make_signed_filename(original: str) -> str:
    """Create a signed filename: report.xlsm → report_signed.xlsm"""
    p = Path(original)
    return f"{p.stem}_signed{p.suffix}"
