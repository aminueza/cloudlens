"""Topology API routes — flat graph, structured graph, and SSE stream."""

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from api.errors import CloudLensError
from api.models import StructuredTopologyResponse, TopologyResponse
from api.ratelimit import limiter
from providers.registry import AuthenticationError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["topology"])


def _check_auth(request: Request) -> None:
    """Check provider authentication state and raise on errors."""
    registry = request.app.state.registry
    errors: list[str] = []
    for name, provider in registry.providers.items():
        err = getattr(provider, "auth_error", None)
        if err:
            errors.append(f"{name}: {err}")
    if errors:
        raise CloudLensError(
            status_code=503,
            detail="Provider authentication errors: " + "; ".join(errors),
        )


@router.get("/api/topology/{scope}", response_model=TopologyResponse)
@limiter.limit("30/minute")
async def get_topology(scope: str, request: Request) -> dict[str, Any]:
    """Return flat topology graph for the given scope."""
    _check_auth(request)
    fetcher = request.app.state.fetcher

    data = fetcher.get_topology(scope)
    if data is None:
        try:
            registry = request.app.state.registry
            data = await registry.fetch_topology(scope)
        except AuthenticationError as exc:
            raise CloudLensError(503, f"Authentication error: {exc}") from exc

    if data is None:
        data = {"nodes": [], "edges": []}

    return {"scope": scope, **data}


@router.get(
    "/api/topology/{scope}/structured", response_model=StructuredTopologyResponse
)
@limiter.limit("30/minute")
async def get_structured_topology(scope: str, request: Request) -> dict[str, Any]:
    """Return hierarchical structured topology for the given scope."""
    _check_auth(request)
    fetcher = request.app.state.fetcher

    data = fetcher.get_structured(scope)
    if data is None:
        try:
            registry = request.app.state.registry
            data = await registry.fetch_structured(scope)
        except AuthenticationError as exc:
            raise CloudLensError(503, f"Authentication error: {exc}") from exc

    if data is None:
        data = {"providers": {}, "cross_cloud_connections": []}

    return {"scope": scope, **data}


@router.get("/api/events")
async def event_stream(request: Request) -> StreamingResponse:
    """Server-Sent Events stream for live topology updates."""
    fetcher = request.app.state.fetcher
    queue: asyncio.Queue[str] = asyncio.Queue()
    fetcher.subscribe(queue)

    async def _generate():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {event}\n\n"
                except TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            fetcher.unsubscribe(queue)

    return StreamingResponse(_generate(), media_type="text/event-stream")
