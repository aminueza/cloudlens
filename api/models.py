"""Pydantic response and request models for CloudLens API."""

from typing import Any

from pydantic import BaseModel, ConfigDict

# --- Error ---


class ErrorResponse(BaseModel):
    error: str


# --- Topology ---


class TopologyResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    scope: str
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]


class StructuredTopologyResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    scope: str
    providers: dict[str, Any]
    cross_cloud_connections: list[dict[str, Any]] = []


# --- Accounts ---


class AccountListResponse(BaseModel):
    accounts: list[str]


# --- Summary ---


class SummaryResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    scope: str
    summary: dict[str, Any]


# --- Changes ---


class ChangeResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    scope: str
    changes: list[dict[str, Any]]
    summary: dict[str, Any] | None = None
    analysis: str | None = None


class SnapshotListResponse(BaseModel):
    scope: str
    snapshots: list[dict[str, Any]]


# --- Health ---


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    scope: str
    checks: list[dict[str, Any]]
    summary: dict[str, Any]
    score: float


class HealthScoreResponse(BaseModel):
    scope: str
    score: float
    summary: dict[str, Any]


# --- Compliance ---


class ComplianceRuleResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    rules: list[dict[str, Any]]


class ViolationResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    scope: str
    violations: list[dict[str, Any]]
    summary: dict[str, Any] | None = None


# --- Blast Radius ---


class BlastRadiusResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    resource_id: str
    scope: str
    affected_resources: list[dict[str, Any]]
    impact_score: float
    impact_summary: str


# --- Incidents ---


class IncidentResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    title: str
    severity: str
    status: str
    scope: str
    description: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    annotations: list[dict[str, Any]] = []
    analysis: str | None = None
    snapshot: dict[str, Any] | None = None
    health_checks: list[dict[str, Any]] | None = None
    changes: list[dict[str, Any]] | None = None


class IncidentListResponse(BaseModel):
    incidents: list[IncidentResponse]


# --- AI ---


class AIQueryRequest(BaseModel):
    question: str
    scope: str = "all"


class AIResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    response: str
    scope: str | None = None


# --- Auth ---


class AuthStatusResponse(BaseModel):
    providers: dict[str, Any]
