"""Health checks, blast radius, anomaly detection, and dependency graph."""

from typing import Any

from fastapi import APIRouter, Request

from api.errors import CloudLensError
from db import repository as repo
from engine.blast_radius import analyze_blast_radius, get_dependency_graph
from engine.health import compute_health_score

router = APIRouter(tags=["health"])


@router.get("/api/health/{scope}")
async def get_health(scope: str) -> dict[str, Any]:
    checks = await repo.get_health_checks(scope)
    summary = await repo.get_health_summary(scope)
    score = compute_health_score(checks)
    return {"checks": checks, "summary": summary, "score": score}


@router.get("/api/health/{scope}/score")
async def get_score(scope: str) -> dict[str, Any]:
    checks = await repo.get_health_checks(scope)
    return compute_health_score(checks)


@router.get("/api/health/{scope}/anomalies")
async def get_anomalies(scope: str, request: Request) -> dict[str, Any]:
    fetcher = request.app.state.fetcher
    structured = fetcher.get_structured(scope)
    if not structured:
        raise CloudLensError(503, "Topology data not available yet")
    changes = await repo.get_changes(scope, limit=50)
    from ai.analyzer import detect_anomalies

    anomalies = await detect_anomalies(structured, changes, scope)
    return {"anomalies": anomalies, "count": len(anomalies)}


@router.get("/api/blast-radius/{resource_id}")
async def blast_radius(
    resource_id: str, request: Request, scope: str = "all"
) -> dict[str, Any]:
    fetcher = request.app.state.fetcher
    structured = fetcher.get_structured(scope)
    if not structured:
        raise CloudLensError(503, "Topology data not available yet")
    return analyze_blast_radius(resource_id, structured)


@router.get("/api/dependencies/{scope}")
async def dependencies(scope: str, request: Request) -> dict[str, Any]:
    fetcher = request.app.state.fetcher
    structured = fetcher.get_structured(scope)
    if not structured:
        raise CloudLensError(503, "Topology data not available yet")
    return get_dependency_graph(structured)
