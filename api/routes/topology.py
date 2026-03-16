"""Topology API routes — flat graph, structured graph, and SSE stream."""

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from api.errors import CloudLensError
from api.ratelimit import limiter

logger = logging.getLogger(__name__)
router = APIRouter(tags=["topology"])


def _check_auth(request: Request) -> None:
    """Check provider auth state, raise 503 if any provider has errors."""
    registry = getattr(request.app.state, "registry", None)
    if not registry:
        return
    errors = registry.get_auth_errors()
    if errors:
        detail = "; ".join(f"{name}: {msg}" for name, msg in errors.items())
        raise CloudLensError(503, detail)


@router.get("/api/topology/{scope}")
@limiter.limit("30/minute")
async def get_topology(scope: str, request: Request) -> dict[str, Any]:
    _check_auth(request)
    fetcher = request.app.state.fetcher
    data: dict[str, Any] = fetcher.get_topology(scope)
    if data is None:
        data = {"nodes": [], "edges": []}
    return data


@router.get("/api/topology/{scope}/structured")
@limiter.limit("30/minute")
async def get_structured_topology(scope: str, request: Request) -> dict[str, Any]:
    _check_auth(request)
    fetcher = request.app.state.fetcher
    data: dict[str, Any] = fetcher.get_structured(scope)
    if data is None:
        data = {
            "networks": [],
            "peerings": [],
            "unlinkedResources": [],
            "unlinkedSecurityGroups": [],
            "stats": {},
        }
    return data


@router.get("/api/events")
async def event_stream(request: Request) -> StreamingResponse:
    """SSE stream — sends update and auth_error events."""
    fetcher = request.app.state.fetcher
    queue: asyncio.Queue[str] = asyncio.Queue()
    fetcher.subscribe(queue)

    async def _generate():
        try:
            # Check auth on connect
            registry = getattr(request.app.state, "registry", None)
            if registry and registry.get_auth_errors():
                errors = registry.get_auth_errors()
                msg = "; ".join(f"{n}: {e}" for n, e in errors.items())
                yield f"event: auth_error\ndata: {msg}\n\n"
            else:
                yield "event: connected\ndata: ok\n\n"

            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    if "auth_error" in event:
                        yield f"event: auth_error\ndata: {event}\n\n"
                    else:
                        yield f"event: update\ndata: {event}\n\n"
                except TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            fetcher.unsubscribe(queue)

    return StreamingResponse(_generate(), media_type="text/event-stream")
