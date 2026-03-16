"""Change-tracking and snapshot routes."""

from typing import Any

from fastapi import APIRouter, Query, Request

from ai.analyzer import analyze_changes
from api.errors import CloudLensError
from api.models import ChangeResponse, SnapshotListResponse, SummaryResponse
from db import repository as repo

router = APIRouter(tags=["changes"])


@router.get("/api/changes/{scope}", response_model=ChangeResponse)
async def list_changes(scope: str, request: Request) -> dict[str, Any]:
    """List recent changes with summary."""
    changes = await repo.get_changes(scope)
    summary = await repo.get_change_summary(scope)
    return {"scope": scope, "changes": changes, "summary": summary}


@router.get("/api/changes/{scope}/summary", response_model=SummaryResponse)
async def change_summary(scope: str, request: Request) -> dict[str, Any]:
    """Return change summary only."""
    summary = await repo.get_change_summary(scope)
    return {"scope": scope, "summary": summary}


@router.get("/api/changes/{scope}/analyze", response_model=ChangeResponse)
async def analyze_scope_changes(scope: str, request: Request) -> dict[str, Any]:
    """AI-powered change analysis."""
    fetcher = request.app.state.fetcher

    changes = await repo.get_changes(scope)
    structured = fetcher.get_structured(scope)
    if structured is None:
        structured = {"providers": {}, "cross_cloud_connections": []}

    analysis = await analyze_changes(changes, structured, scope)
    summary = await repo.get_change_summary(scope)
    return {
        "scope": scope,
        "changes": changes,
        "summary": summary,
        "analysis": analysis,
    }


@router.get("/api/snapshots/{scope}", response_model=SnapshotListResponse)
async def list_snapshots(scope: str, request: Request) -> dict[str, Any]:
    """List available snapshots."""
    snapshots = await repo.list_snapshots(scope)
    return {"scope": scope, "snapshots": snapshots}


@router.get("/api/snapshots/{scope}/at")
async def snapshot_at_time(
    scope: str,
    request: Request,
    timestamp: str = Query(..., description="ISO-8601 timestamp"),
) -> dict[str, Any]:
    """Return topology at a specific point in time."""
    snapshot = await repo.get_snapshot_at(scope, timestamp)
    if snapshot is None:
        raise CloudLensError(
            404, f"No snapshot found for scope '{scope}' at {timestamp}"
        )
    return {"scope": scope, "timestamp": timestamp, "topology": snapshot}
