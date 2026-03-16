"""Health check, anomaly detection, blast-radius, and dependency routes."""

from typing import Any

from engine.dependencies import build_dependency_graph
from fastapi import APIRouter, Query, Request

from ai.analyzer import detect_anomalies
from api.errors import CloudLensError
from api.models import (
    BlastRadiusResponse,
    HealthResponse,
    HealthScoreResponse,
)
from db import repository as repo
from engine.blast_radius import compute_blast_radius
from engine.health import compute_health_score, run_health_checks

router = APIRouter(tags=["health"])


@router.get("/api/health/{scope}", response_model=HealthResponse)
async def health_checks(scope: str, request: Request) -> dict[str, Any]:
    """Run health checks and return results with summary and score."""
    fetcher = request.app.state.fetcher
    structured = fetcher.get_structured(scope) or {"providers": {}}
    checks = run_health_checks(structured, scope)
    score = compute_health_score(checks)
    summary = {
        "total": len(checks),
        "critical": sum(1 for c in checks if c.get("status") == "critical"),
        "warning": sum(1 for c in checks if c.get("status") == "warning"),
        "healthy": sum(1 for c in checks if c.get("status") == "healthy"),
    }
    return {"scope": scope, "checks": checks, "summary": summary, "score": score}


@router.get("/api/health/{scope}/score", response_model=HealthScoreResponse)
async def health_score(scope: str, request: Request) -> dict[str, Any]:
    """Return health score only."""
    fetcher = request.app.state.fetcher
    structured = fetcher.get_structured(scope) or {"providers": {}}
    checks = run_health_checks(structured, scope)
    score = compute_health_score(checks)
    summary = {
        "total": len(checks),
        "critical": sum(1 for c in checks if c.get("status") == "critical"),
        "warning": sum(1 for c in checks if c.get("status") == "warning"),
        "healthy": sum(1 for c in checks if c.get("status") == "healthy"),
    }
    return {"scope": scope, "score": score, "summary": summary}


@router.get("/api/health/{scope}/anomalies")
async def anomalies(scope: str, request: Request) -> dict[str, Any]:
    """AI-powered anomaly detection."""
    fetcher = request.app.state.fetcher
    structured = fetcher.get_structured(scope) or {"providers": {}}
    historical_changes = await repo.get_changes(scope)
    detected = await detect_anomalies(structured, historical_changes, scope)
    return {"scope": scope, "anomalies": detected}


@router.get("/api/blast-radius/{resource_id}", response_model=BlastRadiusResponse)
async def blast_radius(
    resource_id: str,
    request: Request,
    scope: str = Query("all", description="Scope to search within"),
) -> dict[str, Any]:
    """Compute blast radius for a resource."""
    fetcher = request.app.state.fetcher
    topology = fetcher.get_topology(scope)
    if topology is None:
        raise CloudLensError(404, f"No topology data for scope '{scope}'")

    result = compute_blast_radius(resource_id, topology)
    return {
        "resource_id": resource_id,
        "scope": scope,
        "affected_resources": result["affected_resources"],
        "impact_score": result["impact_score"],
        "impact_summary": result["impact_summary"],
    }


@router.get("/api/dependencies/{scope}")
async def dependencies(scope: str, request: Request) -> dict[str, Any]:
    """Return dependency graph for the scope."""
    fetcher = request.app.state.fetcher
    topology = fetcher.get_topology(scope)
    if topology is None:
        return {"scope": scope, "dependencies": {"nodes": [], "edges": []}}

    dep_graph = build_dependency_graph(topology)
    return {"scope": scope, "dependencies": dep_graph}
