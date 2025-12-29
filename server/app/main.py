import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
import traceback

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from app.config import get_settings
from app.logging_config import setup_logging, get_logger
from app.routers import mida_certificate, mida_certificates, mida_imports, convert

# Load settings
settings = get_settings()

# Configure logging
setup_logging(log_level=settings.log_level, log_format=settings.log_format)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    logger.info(
        "Starting application",
        extra={
            "app_name": settings.app_name,
            "version": settings.app_version,
            "environment": settings.environment,
        }
    )
    yield
    logger.info("Shutting down application")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(mida_certificate.router, prefix="/api/mida/certificate", tags=["mida"])
app.include_router(mida_certificates.router, prefix="/api/mida/certificates", tags=["mida-crud"])
app.include_router(mida_imports.router, prefix="/api/mida/imports", tags=["mida-imports"])
app.include_router(convert.router, prefix="/api", tags=["convert"])


# Global exception handler to ensure JSON responses for all errors
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle all unhandled exceptions and return JSON error response."""
    logger.error(
        f"Unhandled exception: {exc}",
        extra={
            "path": request.url.path,
            "method": request.method,
            "traceback": traceback.format_exc(),
        }
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": str(exc),
            "type": type(exc).__name__,
        }
    )


# Serve static files from web directory (for local development)
WEB_DIR = Path(__file__).parent.parent.parent / "web"
if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


@app.get("/")
async def root():
    """Root endpoint - serve the web UI if available."""
    index_file = WEB_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"message": settings.app_name}


@app.get("/health")
async def health():
    """
    Health check endpoint for container orchestration and load balancers.
    Returns 200 OK with basic application info and optional DB status.
    """
    from app.db.session import check_db_connection

    db_ok, db_error = check_db_connection()

    if db_error == "unconfigured":
        db_status = "unconfigured"
        status = "ok"
    elif db_ok:
        db_status = "ok"
        status = "ok"
    else:
        db_status = "error"
        status = "degraded"

    return {
        "status": status,
        "db": db_status,
        "app_name": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
