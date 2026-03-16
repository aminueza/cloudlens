"""Compliance rules, violations, and AI recommendations."""

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ai.analyzer import generate_compliance_recommendations
from api.models import ComplianceRuleResponse, ViolationResponse
from engine.compliance import (
    evaluate_compliance,
    get_compliance_rules,
    get_violations,
    upsert_compliance_rule,
)

router = APIRouter(tags=["compliance"])


class RuleCreate(BaseModel):
    name: str
    description: str = ""
    severity: str = "medium"
    provider: str = "all"
    resource_type: str = ""
    condition: dict[str, Any] = {}
    enabled: bool = True


@router.get("/api/compliance/rules", response_model=ComplianceRuleResponse)
async def list_rules(request: Request) -> dict[str, Any]:
    """List all compliance rules."""
    rules = get_compliance_rules()
    return {"rules": rules}


@router.post("/api/compliance/rules", response_model=ComplianceRuleResponse)
async def create_rule(body: RuleCreate, request: Request) -> dict[str, Any]:
    """Create or update a compliance rule."""
    upsert_compliance_rule(body.model_dump())
    rules = get_compliance_rules()
    return {"rules": rules}


@router.get("/api/compliance/violations/{scope}", response_model=ViolationResponse)
async def list_violations(scope: str, request: Request) -> dict[str, Any]:
    """List compliance violations for a scope."""
    violations = get_violations(scope)
    summary = {
        "total": len(violations),
        "critical": sum(1 for v in violations if v.get("severity") == "critical"),
        "high": sum(1 for v in violations if v.get("severity") == "high"),
        "medium": sum(1 for v in violations if v.get("severity") == "medium"),
        "low": sum(1 for v in violations if v.get("severity") == "low"),
    }
    return {"scope": scope, "violations": violations, "summary": summary}


@router.post("/api/compliance/evaluate/{scope}", response_model=ViolationResponse)
async def evaluate(scope: str, request: Request) -> dict[str, Any]:
    """Evaluate compliance rules against current topology."""
    fetcher = request.app.state.fetcher
    structured = fetcher.get_structured(scope) or {"providers": {}}
    violations = evaluate_compliance(structured, scope)
    summary = {
        "total": len(violations),
        "critical": sum(1 for v in violations if v.get("severity") == "critical"),
        "high": sum(1 for v in violations if v.get("severity") == "high"),
        "medium": sum(1 for v in violations if v.get("severity") == "medium"),
        "low": sum(1 for v in violations if v.get("severity") == "low"),
    }
    return {"scope": scope, "violations": violations, "summary": summary}


@router.get("/api/compliance/recommendations/{scope}")
async def recommendations(scope: str, request: Request) -> dict[str, Any]:
    """AI-powered compliance remediation recommendations."""
    fetcher = request.app.state.fetcher
    structured = fetcher.get_structured(scope) or {"providers": {}}
    violations = get_violations(scope)
    recs = await generate_compliance_recommendations(violations, structured, scope)
    return {"scope": scope, "recommendations": recs}
