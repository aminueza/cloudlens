"""Incident management — persisted in SQLite, not in-memory."""

from typing import Any

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from api.errors import CloudLensError
from db import repository as repo
from engine.health import run_health_checks

router = APIRouter(tags=["incidents"])


class IncidentCreate(BaseModel):
    title: str
    severity: str = "medium"
    description: str = ""
    scope: str | None = None


class IncidentUpdate(BaseModel):
    title: str | None = None
    severity: str | None = None
    status: str | None = None
    description: str | None = None


class AnnotationCreate(BaseModel):
    content: str
    author: str = "user"
    node_id: str | None = None


@router.post("/api/incidents")
async def create_incident(body: IncidentCreate, request: Request) -> dict[str, Any]:
    scope = body.scope or "all"
    fetcher = request.app.state.fetcher

    # Capture snapshot
    snapshot_id = None
    structured = fetcher.get_structured(scope)
    if structured:
        import json

        snapshot_id = await repo.save_snapshot(
            scope=scope,
            graph_json=json.dumps(structured),
            structured_json=json.dumps(structured),
        )

    incident_id = await repo.create_incident(
        scope=scope,
        title=body.title,
        severity=body.severity,
        description=body.description,
    )

    await repo.add_annotation(
        incident_id, "Incident created. Topology snapshot captured.", author="system"
    )

    # Auto-enrich with health issues
    if structured:
        health = run_health_checks(scope, structured)
        issues = [c for c in health if c.get("status") != "healthy"]
        if issues:
            summary = "\n".join(
                f"[{c['status'].upper()}] {c.get('message', '')}" for c in issues[:15]
            )
            await repo.add_annotation(
                incident_id,
                f"Health issues ({len(issues)}):\n{summary}",
                author="system",
            )

    # Auto-enrich with recent changes
    changes = await repo.get_changes(scope, limit=10)
    if changes:
        summary = "\n".join(
            f"[{c.get('change_type', '?').upper()}] {c.get('resource_type', '?')}: {c.get('resource_name', '?')}"
            for c in changes[:10]
        )
        await repo.add_annotation(
            incident_id, f"Recent changes ({len(changes)}):\n{summary}", author="system"
        )

    # AI analysis (non-blocking)
    try:
        if structured:
            from ai.analyzer import analyze_incident as ai_analyze

            inc = await repo.get_incident(incident_id)
            if inc:
                analysis = await ai_analyze(
                    inc, structured, changes, health if structured else []
                )
                if analysis:
                    await repo.add_annotation(
                        incident_id, f"AI Analysis:\n{analysis}", author="ai"
                    )
    except Exception:
        pass  # AI is optional

    return {"id": incident_id, "snapshot_id": snapshot_id}


@router.get("/api/incidents")
async def list_incidents(
    status: str | None = None, scope: str | None = None, limit: int = Query(50, le=200)
) -> dict[str, Any]:
    return {
        "incidents": await repo.list_incidents(
            status=status, scope=scope or "all", limit=limit
        )
    }


@router.get("/api/incidents/{incident_id}")
async def get_incident(incident_id: int) -> dict[str, Any]:
    inc = await repo.get_incident(incident_id)
    if not inc:
        raise CloudLensError(404, "Incident not found")
    return inc


@router.patch("/api/incidents/{incident_id}")
async def update_incident(incident_id: int, body: IncidentUpdate) -> dict[str, Any]:
    inc = await repo.get_incident(incident_id)
    if not inc:
        raise CloudLensError(404, "Incident not found")
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if updates:
        await repo.update_incident(incident_id, **updates)
    return {"status": "updated"}


@router.post("/api/incidents/{incident_id}/annotations")
async def add_annotation(incident_id: int, body: AnnotationCreate) -> dict[str, Any]:
    inc = await repo.get_incident(incident_id)
    if not inc:
        raise CloudLensError(404, "Incident not found")
    ann_id = await repo.add_annotation(incident_id, body.content, author=body.author)
    return {"id": ann_id}


@router.post("/api/incidents/{incident_id}/analyze")
async def analyze_incident_rca(incident_id: int, request: Request) -> dict[str, Any]:
    inc = await repo.get_incident(incident_id)
    if not inc:
        raise CloudLensError(404, "Incident not found")

    scope = inc.get("scope", "all")
    fetcher = request.app.state.fetcher
    structured = fetcher.get_structured(scope) or {}
    changes = await repo.get_changes(scope, limit=50)
    health = await repo.get_health_checks(scope)

    from ai.analyzer import analyze_incident as ai_analyze

    analysis = await ai_analyze(inc, structured, changes, health)
    await repo.add_annotation(incident_id, f"AI Analysis:\n{analysis}", author="ai")
    return {"analysis": analysis}


@router.get("/api/incidents/{incident_id}/timeline")
async def incident_timeline(incident_id: int) -> dict[str, Any]:
    inc = await repo.get_incident(incident_id)
    if not inc:
        raise CloudLensError(404, "Incident not found")
    scope = inc.get("scope", "all")
    changes = await repo.get_changes(scope, limit=50)

    timeline = []
    for a in inc.get("annotations", []):
        timeline.append(
            {"time": a.get("created_at", ""), "type": "annotation", "data": a}
        )
    for c in changes:
        timeline.append(
            {
                "time": c.get("detected_at", c.get("created_at", "")),
                "type": "change",
                "data": c,
            }
        )
    timeline.sort(key=lambda x: x.get("time", ""))
    return {"timeline": timeline}
