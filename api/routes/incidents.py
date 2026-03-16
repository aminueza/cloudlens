"""Incident management with auto-enrichment and AI analysis."""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ai.analyzer import analyze_incident
from api.errors import CloudLensError
from api.models import IncidentListResponse, IncidentResponse
from db import repository as repo
from engine.health import run_health_checks

router = APIRouter(tags=["incidents"])

# In-memory incident store (replace with DB in production)
_incidents: dict[str, dict[str, Any]] = {}


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
    author: str = "system"
    content: str = ""


@router.post("/api/incidents", response_model=IncidentResponse)
async def create_incident(body: IncidentCreate, request: Request) -> dict[str, Any]:
    """Create an incident with auto-enrichment."""
    scope = body.scope or "all"
    fetcher = request.app.state.fetcher
    now = datetime.now(UTC).isoformat()
    incident_id = str(uuid.uuid4())

    # Auto-enrichment: capture snapshot, health checks, recent changes
    structured = fetcher.get_structured(scope) or {"providers": {}}
    topology_snapshot = fetcher.get_topology(scope)
    health = run_health_checks(scope, structured)
    changes = await repo.get_changes(scope)

    # AI analysis
    incident_data: dict[str, Any] = {
        "id": incident_id,
        "title": body.title,
        "severity": body.severity,
        "description": body.description,
        "scope": scope,
        "status": "open",
        "created_at": now,
        "updated_at": now,
        "annotations": [],
        "snapshot": topology_snapshot,
        "health_checks": health,
        "changes": changes,
        "analysis": None,
    }

    analysis = await analyze_incident(incident_data, structured, changes, health)
    incident_data["analysis"] = analysis

    _incidents[incident_id] = incident_data
    return incident_data


@router.get("/api/incidents", response_model=IncidentListResponse)
async def list_incidents(request: Request) -> dict[str, Any]:
    """List all incidents."""
    return {"incidents": list(_incidents.values())}


@router.get("/api/incidents/{incident_id}", response_model=IncidentResponse)
async def get_incident(incident_id: str, request: Request) -> dict[str, Any]:
    """Get incident detail with annotations."""
    incident = _incidents.get(incident_id)
    if incident is None:
        raise CloudLensError(404, f"Incident '{incident_id}' not found")
    return incident


@router.patch("/api/incidents/{incident_id}", response_model=IncidentResponse)
async def update_incident(
    incident_id: str, body: IncidentUpdate, request: Request
) -> dict[str, Any]:
    """Update an incident."""
    incident = _incidents.get(incident_id)
    if incident is None:
        raise CloudLensError(404, f"Incident '{incident_id}' not found")

    updates = body.model_dump(exclude_none=True)
    incident.update(updates)
    incident["updated_at"] = datetime.now(UTC).isoformat()
    return incident


@router.post(
    "/api/incidents/{incident_id}/annotations", response_model=IncidentResponse
)
async def add_annotation(
    incident_id: str, body: AnnotationCreate, request: Request
) -> dict[str, Any]:
    """Add an annotation to an incident."""
    incident = _incidents.get(incident_id)
    if incident is None:
        raise CloudLensError(404, f"Incident '{incident_id}' not found")

    annotation = {
        "author": body.author,
        "content": body.content,
        "created_at": datetime.now(UTC).isoformat(),
    }
    incident["annotations"].append(annotation)
    incident["updated_at"] = datetime.now(UTC).isoformat()
    return incident


@router.post("/api/incidents/{incident_id}/analyze", response_model=IncidentResponse)
async def analyze_incident_rca(incident_id: str, request: Request) -> dict[str, Any]:
    """Run AI root-cause analysis on an incident."""
    incident = _incidents.get(incident_id)
    if incident is None:
        raise CloudLensError(404, f"Incident '{incident_id}' not found")

    scope = incident.get("scope", "all")
    fetcher = request.app.state.fetcher
    structured = fetcher.get_structured(scope) or {"providers": {}}
    changes = incident.get("changes") or await repo.get_changes(scope)
    health = incident.get("health_checks") or run_health_checks(scope, structured)

    analysis = await analyze_incident(incident, structured, changes, health)
    incident["analysis"] = analysis
    incident["updated_at"] = datetime.now(UTC).isoformat()
    return incident


@router.get("/api/incidents/{incident_id}/timeline")
async def incident_timeline(incident_id: str, request: Request) -> dict[str, Any]:
    """Get timeline of events for an incident."""
    incident = _incidents.get(incident_id)
    if incident is None:
        raise CloudLensError(404, f"Incident '{incident_id}' not found")

    timeline: list[dict[str, Any]] = []

    # Creation event
    timeline.append(
        {
            "event": "incident_created",
            "timestamp": incident["created_at"],
            "detail": f"Incident created: {incident['title']}",
        }
    )

    # Annotation events
    for ann in incident.get("annotations", []):
        timeline.append(
            {
                "event": "annotation_added",
                "timestamp": ann.get("created_at", ""),
                "detail": f"{ann.get('author', 'unknown')}: {ann.get('content', '')}",
            }
        )

    # Related changes
    for change in (incident.get("changes") or [])[:20]:
        timeline.append(
            {
                "event": "topology_change",
                "timestamp": change.get("timestamp", ""),
                "detail": (
                    f"{change.get('action', '?')} {change.get('resource_type', '?')} "
                    f"{change.get('resource_id', '?')}"
                ),
            }
        )

    timeline.sort(key=lambda e: e.get("timestamp", ""))
    return {"incident_id": incident_id, "timeline": timeline}
