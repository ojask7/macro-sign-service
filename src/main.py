"""
Macro Sign Service - Main FastAPI Application
Enterprise-grade macro signing service for VBA digital signing.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.config.logging import get_logger, setup_logging
from src.config.settings import get_settings

# Initialize logging
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup/shutdown."""
    settings = get_settings()
    logger.info(
        "Starting Macro Sign Service",
        version=settings.app.version,
        environment=settings.app.env.value,
    )

    # Initialize database
    try:
        from src.models.database import init_db

        await init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.warning("Database initialization skipped", error=str(e))

    # Generate dev certificates if needed
    if not settings.app.is_production:
        try:
            from pathlib import Path

            from src.core.signing_engine import create_self_signed_cert

            cert_dir = Path("./certs")
            cert_dir.mkdir(parents=True, exist_ok=True)

            # Default signing certificate
            cert_path = cert_dir / "default.pem"
            key_path = cert_dir / "default.key"
            if not cert_path.exists():
                cert_pem, key_pem = create_self_signed_cert()
                cert_path.write_bytes(cert_pem)
                key_path.write_bytes(key_pem)
                logger.info("Development self-signed certificate generated")

            # SNOW test-domain certificate (auto-provisioned for ServiceNow integration)
            snow_cert_path = cert_dir / "snow-test-domain.pem"
            snow_key_path = cert_dir / "snow-test-domain.key"
            if not snow_cert_path.exists():
                snow_cert_pem, snow_key_pem = create_self_signed_cert(
                    common_name="snow-test.macro-sign.local",
                    organization="SNOW Test Domain",
                    days_valid=365,
                )
                snow_cert_path.write_bytes(snow_cert_pem)
                snow_key_path.write_bytes(snow_key_pem)
                logger.info("SNOW test-domain certificate generated")
        except Exception as e:
            logger.warning("Failed to generate dev certificate", error=str(e))

    yield

    # Shutdown
    try:
        from src.models.database import close_db

        await close_db()
        logger.info("Database connections closed")
    except Exception:
        pass

    logger.info("Macro Sign Service stopped")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="Macro Sign Service",
        description=(
            "Enterprise-grade macro signing service that automates digital "
            "signing of Office macros (VBA) for security compliance."
        ),
        version=settings.app.version,
        docs_url="/api/docs" if not settings.app.is_production else None,
        redoc_url="/api/redoc" if not settings.app.is_production else None,
        openapi_url="/api/openapi.json" if not settings.app.is_production else None,
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors.origins_list,
        allow_credentials=settings.cors.allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Prometheus metrics
    try:
        from prometheus_fastapi_instrumentator import Instrumentator

        Instrumentator(
            should_group_status_codes=True,
            should_group_untemplated=True,
        ).instrument(app).expose(app, endpoint="/metrics")
    except Exception:
        logger.warning("Prometheus instrumentation not available")

    # Request ID middleware
    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        import uuid

        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = request_id

        # Add rate limit headers if present
        if hasattr(request.state, "rate_limit_headers"):
            for key, value in request.state.rate_limit_headers.items():
                response.headers[key] = value

        return response

    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(
            "Unhandled exception",
            path=request.url.path,
            method=request.method,
            error=str(exc),
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "detail": str(exc) if settings.app.debug else "An unexpected error occurred",
            },
        )

    # Register API routes
    from src.api.admin import (
        router_audit,
        router_dashboard,
        router_profiles,
        router_teams,
        router_users,
    )
    from src.api.auth import router as auth_router
    from src.api.health import router as health_router
    from src.api.signing import router as signing_router
    from src.api.signing import router_status, router_verify
    from src.api.snow import router as snow_router
    from src.api.webhooks import router as webhooks_router

    api_prefix = "/api/v1"

    app.include_router(health_router, prefix=api_prefix)
    app.include_router(auth_router, prefix=api_prefix)
    app.include_router(signing_router, prefix=api_prefix)
    app.include_router(router_status, prefix=api_prefix)
    app.include_router(router_verify, prefix=api_prefix)
    app.include_router(snow_router, prefix=api_prefix)
    app.include_router(webhooks_router, prefix=api_prefix)
    app.include_router(router_users, prefix=api_prefix)
    app.include_router(router_teams, prefix=api_prefix)
    app.include_router(router_profiles, prefix=api_prefix)
    app.include_router(router_audit, prefix=api_prefix)
    app.include_router(router_dashboard, prefix=api_prefix)

    # Root redirect to docs
    @app.get("/", include_in_schema=False)
    async def root():
        return {
            "service": "Macro Sign Service",
            "version": settings.app.version,
            "docs": "/api/docs",
            "health": "/api/v1/health",
        }

    return app


app = create_app()
