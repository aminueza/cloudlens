"""Authentication middleware for CloudLens."""

import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from config.settings import settings

logger = logging.getLogger(__name__)

_PUBLIC_PREFIXES = tuple(
    p.strip() for p in settings.CLOUDLENS_AUTH_PUBLIC_PATHS.split(",") if p.strip()
)


class AuthMiddleware(BaseHTTPMiddleware):
    """API key auth. If CLOUDLENS_AUTH_DISABLED=true, passes through.
    If CLOUDLENS_API_KEY is set, validates X-API-Key or Bearer token against it.
    If CLOUDLENS_API_KEY is empty and auth is enabled, rejects all requests."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if settings.CLOUDLENS_AUTH_DISABLED:
            return await call_next(request)

        path = request.url.path
        if path == "/" or any(path.startswith(p) for p in _PUBLIC_PREFIXES):
            return await call_next(request)

        configured_key = settings.CLOUDLENS_API_KEY
        if not configured_key:
            # No key configured but auth enabled — reject
            return JSONResponse(
                {"error": "CLOUDLENS_API_KEY not configured"}, status_code=500
            )

        # Check X-API-Key header
        api_key = request.headers.get("X-API-Key", "").strip()
        if api_key and api_key == configured_key:
            return await call_next(request)

        # Check Authorization: Bearer <token>
        auth_header = request.headers.get("Authorization", "").strip()
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()
            if token and token == configured_key:
                return await call_next(request)

        logger.warning("Unauthenticated request to %s %s", request.method, path)
        return JSONResponse({"error": "Invalid or missing API key"}, status_code=401)
