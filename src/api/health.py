"""
Health check endpoint.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from src.config.settings import get_settings
from src.models.pydantic_schemas import HealthResponse

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health Check",
    description="Check the health status of the service and its dependencies.",
)
async def health_check() -> HealthResponse:
    """Health check endpoint for load balancers and monitoring."""
    settings = get_settings()
    checks: dict[str, str] = {}

    # Check database connectivity
    try:
        from src.models.database import get_engine

        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        checks["database"] = "healthy"
    except Exception as e:
        checks["database"] = f"unhealthy: {str(e)[:100]}"

    # Check Redis connectivity
    try:
        import redis as redis_lib

        r = redis_lib.from_url(settings.redis.url, socket_timeout=2)
        r.ping()
        checks["redis"] = "healthy"
    except Exception as e:
        checks["redis"] = f"unhealthy: {str(e)[:100]}"

    # Determine overall status
    all_healthy = all(v == "healthy" for v in checks.values())
    overall_status = "healthy" if all_healthy else "degraded"

    return HealthResponse(
        status=overall_status,
        version=settings.app.version,
        environment=settings.app.env.value,
        timestamp=datetime.now(timezone.utc),
        checks=checks,
    )


@router.get(
    "/ready",
    summary="Readiness Check",
    description="Check if the service is ready to accept traffic.",
)
async def readiness_check() -> dict:
    """Readiness probe for Kubernetes."""
    return {"ready": True}


@router.get(
    "/live",
    summary="Liveness Check",
    description="Check if the service is alive.",
)
async def liveness_check() -> dict:
    """Liveness probe for Kubernetes."""
    return {"alive": True}
