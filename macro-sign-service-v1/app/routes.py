"""API routes for the macro signing service."""

from __future__ import annotations

import base64
import logging
import sys
import time
from typing import Optional

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse

from app import audit, signing
from app.certs import CertStore, CertStoreError
from app.config import get_settings
from app.validator import FileValidationError, validate_file

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")

# Will be set during app startup
_cert_store: Optional[CertStore] = None


def set_cert_store(store: CertStore) -> None:
    global _cert_store
    _cert_store = store


def get_cert_store() -> CertStore:
    if _cert_store is None:
        raise HTTPException(status_code=503, detail="Certificate store not initialized")
    return _cert_store


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------


async def check_api_key(x_api_key: Optional[str] = Header(None)) -> Optional[str]:
    """Validate API key if configured. Returns the key or None."""
    settings = get_settings()
    if not settings.api_key:
        return None  # Auth disabled
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return x_api_key


# ---------------------------------------------------------------------------
# POST /sign
# ---------------------------------------------------------------------------


@router.post("/sign")
async def sign_file_endpoint(
    file: UploadFile = File(...),
    cert_name: Optional[str] = Query(None),
    algorithm: str = Query("SHA256"),
    requester_id: Optional[str] = Query(None),
    _key: Optional[str] = Depends(check_api_key),
):
    """Upload a macro file and receive the signed version."""
    settings = get_settings()
    store = get_cert_store()
    cert_name = cert_name or settings.default_cert_name
    start = time.monotonic()

    filename = file.filename or "unknown"
    content = await file.read()

    # Validate
    try:
        warnings = validate_file(filename, content)
    except FileValidationError as e:
        await audit.log_event("sign", "validation_error", filename=filename, error=str(e))
        raise HTTPException(status_code=400, detail=str(e))

    # Get cert
    try:
        pfx_bytes = store.get_pfx(cert_name)
        fingerprint = store.get_fingerprint(cert_name)
    except CertStoreError as e:
        raise HTTPException(status_code=404, detail=str(e))

    from pathlib import Path
    ext = Path(filename).suffix.lower()

    try:
        if ext in settings.office_extensions:
            # Office file → signtool
            signed_bytes, metadata = await signing.sign_office_file(
                file_bytes=content,
                filename=filename,
                pfx_bytes=pfx_bytes,
                pfx_password=settings.pfx_password,
                hash_algorithm=algorithm.upper(),
            )
            duration_ms = int((time.monotonic() - start) * 1000)
            await audit.log_event(
                "sign", "success",
                filename=filename, file_size=len(content),
                signing_method="signtool-office-sip",
                certificate_fingerprint=fingerprint,
                algorithm=algorithm, requester_id=requester_id,
                duration_ms=duration_ms,
            )
            return {
                "file_b64": base64.b64encode(signed_bytes).decode(),
                "filename": filename,
                "signing_method": metadata["signing_method"],
                "certificate_fingerprint": fingerprint,
                "algorithm": algorithm,
                "signed_at": metadata["signed_at"],
                "verification_passed": metadata.get("verification_passed"),
                "warnings": warnings or None,
            }

        elif ext in settings.text_macro_extensions:
            # Text macro → RSA detached signature
            original, signature, metadata = await signing.sign_text_macro(
                content=content,
                pfx_bytes=pfx_bytes,
                pfx_password=settings.pfx_password,
                hash_algorithm=algorithm.upper(),
            )
            duration_ms = int((time.monotonic() - start) * 1000)
            await audit.log_event(
                "sign", "success",
                filename=filename, file_size=len(content),
                signing_method="rsa-detached",
                certificate_fingerprint=fingerprint,
                algorithm=algorithm, requester_id=requester_id,
                duration_ms=duration_ms,
            )
            return {
                "file_b64": base64.b64encode(original).decode(),
                "signature_b64": base64.b64encode(signature).decode(),
                "filename": filename,
                "signing_method": "rsa-detached",
                "certificate_fingerprint": fingerprint,
                "algorithm": algorithm,
                "signed_at": metadata["signed_at"],
                "warnings": warnings or None,
            }
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported extension '{ext}' for signing",
            )

    except signing.SigningError as e:
        duration_ms = int((time.monotonic() - start) * 1000)
        await audit.log_event(
            "sign", "error",
            filename=filename, file_size=len(content),
            certificate_fingerprint=fingerprint,
            algorithm=algorithm, requester_id=requester_id,
            error=str(e), duration_ms=duration_ms,
        )
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# POST /verify
# ---------------------------------------------------------------------------


@router.post("/verify")
async def verify_file_endpoint(
    file: UploadFile = File(...),
    _key: Optional[str] = Depends(check_api_key),
):
    """Verify a signed Office file using signtool."""
    filename = file.filename or "unknown"
    content = await file.read()

    try:
        result = await signing.verify_file(content, filename)
    except signing.SigningError as e:
        raise HTTPException(status_code=503, detail=str(e))

    await audit.log_event(
        "verify", "success" if result["valid"] else "invalid",
        filename=filename, file_size=len(content),
    )
    return result


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------


@router.get("/health")
async def health_endpoint():
    """Health check — reports signtool, Office SIP, and cert status."""
    store = get_cert_store()
    sip_info = await __import__("asyncio").to_thread(signing.check_office_sip)

    certs_loaded = len(store.list_certs())
    signing_ready = (
        sip_info["signtool_found"]
        and sip_info["office_sip_status"] in ("found", "registered")
    )

    status = "healthy" if signing_ready and certs_loaded > 0 else "degraded"
    status_code = 200 if status == "healthy" else 503

    return JSONResponse(
        content={
            "status": status,
            "platform": sys.platform,
            "signing_ready": signing_ready,
            "certificates_loaded": certs_loaded,
            **sip_info,
        },
        status_code=status_code,
    )


# ---------------------------------------------------------------------------
# GET /certs
# ---------------------------------------------------------------------------


@router.get("/certs")
async def list_certs_endpoint(
    _key: Optional[str] = Depends(check_api_key),
):
    """List all available certificates."""
    store = get_cert_store()
    return {"certificates": store.list_certs()}


@router.get("/certs/{name}")
async def get_cert_endpoint(
    name: str,
    _key: Optional[str] = Depends(check_api_key),
):
    """Get details for a specific certificate."""
    store = get_cert_store()
    try:
        return store.get_cert(name)
    except CertStoreError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ---------------------------------------------------------------------------
# GET /audit
# ---------------------------------------------------------------------------


@router.get("/audit")
async def audit_endpoint(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    action: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    _key: Optional[str] = Depends(check_api_key),
):
    """Query audit logs."""
    logs = await audit.query_logs(
        limit=limit, offset=offset, action=action, status=status,
    )
    return {"logs": logs, "count": len(logs)}
