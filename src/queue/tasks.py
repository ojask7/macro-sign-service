"""
Celery tasks for async signing operations.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from src.config.logging import get_logger
from src.queue.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(
    bind=True,
    name="src.queue.tasks.sign_macro_task",
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
)
def sign_macro_task(
    self,
    job_id: str,
    file_content_hex: str,
    certificate_name: str,
    algorithm: str = "sha256",
    webhook_url: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Async task to sign a macro file.

    Args:
        job_id: Unique job identifier
        file_content_hex: Hex-encoded file content
        certificate_name: Name of the certificate to use
        algorithm: Hash algorithm
        webhook_url: Optional webhook to notify on completion
        metadata: Optional metadata

    Returns:
        Dictionary with signing results
    """
    start_time = time.time()

    try:
        logger.info(
            "Starting signing task",
            job_id=job_id,
            certificate=certificate_name,
            algorithm=algorithm,
        )

        # Import here to avoid circular imports
        from src.core.certificate_store import get_certificate_store
        from src.core.signing_engine import SigningEngine

        file_content = bytes.fromhex(file_content_hex)

        # Get certificate from store
        import asyncio

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            cert_store = get_certificate_store()
            cert_info = loop.run_until_complete(
                cert_store.get_certificate(certificate_name)
            )
        finally:
            loop.close()

        # Check if this is an Office macro file that should use VBA signing
        from pathlib import Path as _Path
        from src.config.settings import get_settings

        _settings = get_settings()
        _vba_extensions = {".xlsm", ".xlsb", ".docm", ".pptm", ".xltm", ".dotm", ".potm"}
        _original_filename = metadata.get("original_filename", "") if metadata else ""
        _ext = _Path(_original_filename).suffix.lower() if _original_filename else ""

        if _settings.signing.use_vba_signing and _ext in _vba_extensions:
            from src.core.vba_signing import VBASigningEngine

            vba_engine = VBASigningEngine(
                certificate_pem=cert_info.certificate_pem,
                private_key_pem=cert_info.private_key_pem,
                pfx_password=_settings.signing.pfx_password,
            )
            vba_result = vba_engine.sign_file(
                file_content, _original_filename, algorithm=algorithm
            )
            elapsed = time.time() - start_time

            import base64
            signing_result = {
                "job_id": job_id,
                "status": "completed",
                "signed_file_b64": base64.b64encode(vba_result.signed_file_bytes).decode(),
                "certificate_fingerprint": vba_result.certificate_fingerprint,
                "certificate_subject": vba_result.certificate_subject,
                "algorithm": vba_result.algorithm,
                "signing_method": vba_result.signing_method,
                "signed_at": vba_result.signed_at.isoformat(),
                "elapsed_seconds": round(elapsed, 3),
            }
        else:
            # Standard detached signature for text-based macro files
            engine = SigningEngine(
                private_key_pem=cert_info.private_key_pem,
                certificate_pem=cert_info.certificate_pem,
            )

            result = engine.sign(file_content, algorithm=algorithm, metadata=metadata)
            elapsed = time.time() - start_time

            signing_result = {
                "job_id": job_id,
                "status": "completed",
                "signature": result.signature.hex(),
                "file_hash": result.file_hash,
                "certificate_fingerprint": result.certificate_fingerprint,
                "algorithm": result.algorithm,
                "signed_at": result.signed_at.isoformat(),
                "elapsed_seconds": round(elapsed, 3),
            }

        logger.info(
            "Signing task completed",
            job_id=job_id,
            elapsed_seconds=round(elapsed, 3),
        )

        # Send webhook notification if configured
        if webhook_url:
            send_webhook_task.delay(
                webhook_url=webhook_url,
                event="signing.completed",
                payload=signing_result,
            )

        return signing_result

    except Exception as exc:
        elapsed = time.time() - start_time
        logger.error(
            "Signing task failed",
            job_id=job_id,
            error=str(exc),
            elapsed_seconds=round(elapsed, 3),
        )

        error_result = {
            "job_id": job_id,
            "status": "failed",
            "error": str(exc),
            "elapsed_seconds": round(elapsed, 3),
        }

        # Send failure webhook if configured
        if webhook_url:
            send_webhook_task.delay(
                webhook_url=webhook_url,
                event="signing.failed",
                payload=error_result,
            )

        # Retry on transient errors
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)

        return error_result


@celery_app.task(
    bind=True,
    name="src.queue.tasks.verify_macro_task",
    max_retries=2,
    default_retry_delay=10,
)
def verify_macro_task(
    self,
    file_content_hex: str,
    signature_hex: str,
    certificate_pem: Optional[str] = None,
    algorithm: str = "sha256",
) -> dict[str, Any]:
    """
    Async task to verify a signed macro file.
    """
    try:
        from src.core.signing_engine import SigningEngine

        file_content = bytes.fromhex(file_content_hex)
        signature = bytes.fromhex(signature_hex)

        cert_pem = certificate_pem.encode() if certificate_pem else None

        engine = SigningEngine()
        result = engine.verify(
            file_content=file_content,
            signature=signature,
            algorithm=algorithm,
            certificate_pem=cert_pem,
        )

        return result.to_dict()

    except Exception as exc:
        logger.error("Verification task failed", error=str(exc))
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        return {
            "is_valid": False,
            "message": f"Verification failed: {str(exc)}",
        }


@celery_app.task(
    bind=True,
    name="src.queue.tasks.send_webhook_task",
    max_retries=3,
    default_retry_delay=60,
)
def send_webhook_task(
    self,
    webhook_url: str,
    event: str,
    payload: dict[str, Any],
    secret: Optional[str] = None,
) -> dict[str, Any]:
    """
    Send a webhook notification.
    """
    import hashlib
    import hmac

    try:
        headers = {
            "Content-Type": "application/json",
            "X-Macro-Sign-Event": event,
        }

        body = json.dumps(payload)

        # Add HMAC signature if secret is provided
        if secret:
            signature = hmac.new(
                secret.encode(), body.encode(), hashlib.sha256
            ).hexdigest()
            headers["X-Macro-Sign-Signature"] = f"sha256={signature}"

        with httpx.Client(timeout=30.0) as client:
            response = client.post(webhook_url, content=body, headers=headers)
            response.raise_for_status()

        logger.info(
            "Webhook sent successfully",
            url=webhook_url,
            event=event,
            status_code=response.status_code,
        )

        return {
            "status": "sent",
            "status_code": response.status_code,
            "url": webhook_url,
            "event": event,
        }

    except Exception as exc:
        logger.warning(
            "Webhook delivery failed",
            url=webhook_url,
            event=event,
            error=str(exc),
            retry=self.request.retries,
        )

        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)

        return {
            "status": "failed",
            "error": str(exc),
            "url": webhook_url,
            "event": event,
        }
