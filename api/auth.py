"""Authentication middleware for CloudLens.

Simple API-key / bearer-token auth. Multi-cloud — no provider-specific IdP.
"""

import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from config.settings import settings

logger = logging.getLogger(__name__)


class AuthMiddleware(BaseHTTPMiddleware):
    """Lightweight auth gate.

    * If ``settings.CLOUDLENS_AUTH_DISABLED`` is truthy the middleware is a
      pass-through.
    * Public paths (always includes ``/``) are exempt.
    * Otherwise an ``X-API-Key`` header **or** ``Authorization: Bearer <token>``
      must be present and non-empty.  For now any non-empty value is accepted
      (placeholder for a real auth backend).
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Auth disabled — pass through
        if settings.CLOUDLENS_AUTH_DISABLED:
            return await call_next(request)

        path = request.url.path.rstrip("/") or "/"

        # Always-public paths
        public_paths: set[str] = {"/"}
        for p in getattr(settings, "CLOUDLENS_AUTH_PUBLIC_PATHS", []):
            public_paths.add(p.rstrip("/") or "/")

        if path in public_paths:
            return await call_next(request)

        # Check X-API-Key header
        api_key = request.headers.get("X-API-Key", "").strip()
        if api_key:
            return await call_next(request)

        # Check Authorization: Bearer <token>
        auth_header = request.headers.get("Authorization", "").strip()
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()
            if token:
                return await call_next(request)

        logger.warning("Unauthenticated request to %s %s", request.method, path)
        return JSONResponse(
            {"error": "Authentication required"},
            status_code=401,
        )
