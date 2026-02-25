"""Custom middleware for logging, rate limiting, security headers."""

import time
import uuid
import logging
from datetime import datetime
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse
from fastapi import status

from app.config import settings
from app.security import RateLimiter

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("audit")


def get_client_ip(request: Request) -> str:
    """Extract real client IP handling proxies."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip
    return request.client.host if request.client else "unknown"


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log all requests with timing."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = str(uuid.uuid4())[:8]
        request.state.request_id = request_id
        start_time = time.time()

        logger.info(
            f"[{request_id}] {request.method} {request.url.path} "
            f"from {get_client_ip(request)}"
        )

        try:
            response = await call_next(request)
            duration_ms = (time.time() - start_time) * 1000
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time"] = f"{duration_ms:.2f}ms"

            log_level = logging.WARNING if response.status_code >= 400 else logging.INFO
            logger.log(
                log_level,
                f"[{request_id}] {response.status_code} "
                f"{request.url.path} {duration_ms:.2f}ms",
            )
            return response

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                f"[{request_id}] ERROR {request.url.path} "
                f"{duration_ms:.2f}ms: {e}"
            )
            raise


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Global rate limiting per IP."""

    EXEMPT_PATHS = ["/api/v1/health", "/docs", "/openapi.json", "/"]

    def __init__(self, app, max_requests: int = 60, window_seconds: int = 60):
        super().__init__(app)
        self.rate_limiter = RateLimiter(max_requests, window_seconds)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)

        client_ip = get_client_ip(request)

        if not self.rate_limiter.is_allowed(client_ip):
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "Too many requests",
                    "detail": "Please wait before making more requests.",
                },
                headers={"Retry-After": "60"},
            )

        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    HEADERS = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Cache-Control": "no-store, no-cache, must-revalidate",
        "Pragma": "no-cache",
    }

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        for header, value in self.HEADERS.items():
            response.headers[header] = value
        response.headers.pop("Server", None)
        return response


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Enforce request body size limits."""

    def __init__(self, app, max_size_mb: int = 10):
        super().__init__(app)
        self.max_size_bytes = max_size_mb * 1024 * 1024

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > self.max_size_bytes:
                    return JSONResponse(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        content={
                            "error": "File too large",
                            "detail": f"Max size: {self.max_size_bytes // (1024*1024)}MB",
                        },
                    )
            except ValueError:
                pass
        return await call_next(request)


class AuditLogMiddleware(BaseHTTPMiddleware):
    """Create audit logs for sensitive operations."""

    AUDITED_PATHS = {
        "/api/v1/upload": "FILE_UPLOAD",
        "/api/v1/process": "STATEMENT_PROCESS",
        "/api/v1/download": "FILE_DOWNLOAD",
    }

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        for path_prefix, action in self.AUDITED_PATHS.items():
            if request.url.path.startswith(path_prefix):
                audit_logger.info(
                    f"AUDIT | action={action} | "
                    f"ip={get_client_ip(request)} | "
                    f"path={request.url.path} | "
                    f"status={response.status_code} | "
                    f"time={datetime.utcnow().isoformat()}"
                )
                break

        return response