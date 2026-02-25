"""FastAPI application entry point with full middleware stack."""

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.api.routes import router
from app.api.middleware import (
    RequestLoggingMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
    RequestSizeLimitMiddleware,
    AuditLogMiddleware,
)


# ─── Logging Setup ─────────────────────────────────────────────

def setup_logging() -> None:
    fmt = "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s"

    handlers = [logging.StreamHandler(sys.stdout)]

    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    if not settings.DEBUG:
        handlers.append(
            logging.FileHandler(log_dir / "app.log", encoding="utf-8")
        )
        # Separate audit log
        audit_handler = logging.FileHandler(
            log_dir / "audit.log", encoding="utf-8"
        )
        audit_handler.setLevel(logging.INFO)
        audit_logger = logging.getLogger("audit")
        audit_logger.addHandler(audit_handler)
        audit_logger.setLevel(logging.INFO)

    logging.basicConfig(
        level=logging.DEBUG if settings.DEBUG else logging.INFO,
        format=fmt,
        handlers=handlers,
    )

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


setup_logging()
logger = logging.getLogger(__name__)


# ─── Lifespan ──────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 60)
    logger.info(f"Starting {settings.APP_NAME}")
    logger.info(f"Debug: {settings.DEBUG}")
    logger.info("=" * 60)

    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    settings.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Cleanup stale files from previous runs
    for d in [settings.UPLOAD_DIR, settings.OUTPUT_DIR]:
        for f in d.iterdir():
            if f.is_file():
                f.unlink()

    yield

    logger.info("Shutting down...")


# ─── Create Application ───────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        description="Secure MPesa PDF statement processing API",
        version="1.0.0",
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
        openapi_url="/openapi.json" if settings.DEBUG else None,
        lifespan=lifespan,
    )

    # ── Middleware (last added = first executed) ─────────────────
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(RequestSizeLimitMiddleware, max_size_mb=settings.MAX_FILE_SIZE_MB + 1)
    app.add_middleware(SecurityHeadersMiddleware)

    if not settings.DEBUG:
        app.add_middleware(AuditLogMiddleware)

    app.add_middleware(
        RateLimitMiddleware,
        max_requests=settings.RATE_LIMIT_PER_MINUTE,
        window_seconds=60,
    )
    app.add_middleware(RequestLoggingMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "X-Process-Time"],
        max_age=600,
    )

    # ── Exception handlers ──────────────────────────────────────

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.detail, "status_code": exc.status_code},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        logger.warning(f"Validation: {exc.errors()}")
        messages = [
            f"Invalid: {'.'.join(str(l) for l in e.get('loc', []))}"
            for e in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={"error": "Validation Error", "detail": messages[:5]},
        )

    @app.exception_handler(Exception)
    async def global_error(request: Request, exc: Exception):
        logger.exception(f"Unhandled: {type(exc).__name__}")
        return JSONResponse(
            status_code=500,
            content={"error": "Internal error. Please try again."},
        )

    # ── Routes ──────────────────────────────────────────────────
    app.include_router(router)

    @app.get("/", include_in_schema=False)
    async def root():
        return {
            "app": settings.APP_NAME,
            "health": "/api/v1/health",
            "docs": "/docs" if settings.DEBUG else "disabled",
        }

    return app


app = create_app()


# ─── Run directly ──────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
    )