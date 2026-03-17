"""FastAPI application — entry point for the macro signing service."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from app import __version__
from app.audit import close_db, init_db
from app.certs import CertStore
from app.config import get_settings
from app.routes import router, set_cert_store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
log = logging.getLogger("macro-sign-service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    settings = get_settings()

    # Init cert store
    store = CertStore()
    store.init()
    set_cert_store(store)
    log.info("Certificate store ready: %d cert(s)", len(store.list_certs()))

    # Init audit DB
    await init_db()

    log.info("macro-sign-service v%s ready on %s:%d", __version__, settings.host, settings.port)
    yield

    # Shutdown
    await close_db()
    log.info("Shutdown complete")


app = FastAPI(
    title="Macro Sign Service",
    version=__version__,
    description="Windows-native Office VBA macro signing service",
    lifespan=lifespan,
)
app.include_router(router)


@app.get("/")
async def root():
    return {"service": "macro-sign-service", "version": __version__}


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )
