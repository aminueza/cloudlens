"""Compliance rules, violations, and AI recommendations."""

import json as json_mod
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from api.errors import CloudLensError
from db import repository as repo
from engine.compliance import evaluate_rules

router = APIRouter(tags=["compliance"])


class RuleCreate(BaseModel):
    name: str
    description: str = ""
    severity: str = "warning"
    rule_type: str = "require_resource"
    rule_config: dict[str, Any] = {}
    enabled: bool = True


@router.get("/api/compliance/rules")
async def list_rules() -> dict[str, Any]:
    rules = await repo.list_compliance_rules("all")
    return {"rules": rules}


@router.post("/api/compliance/rules")
async def create_rule(body: RuleCreate) -> dict[str, Any]:
    rule_id = f"{body.rule_type}_{body.name}".replace(" ", "_").lower()
    params = json_mod.dumps({"rule_type": body.rule_type, **body.rule_config})
    await repo.upsert_compliance_rule(
        rule_id=rule_id,
        scope="all",
        name=body.name,
        description=body.description,
        severity=body.severity,
        enabled=body.enabled,
        params=params,
    )
    return {"id": rule_id, "status": "created"}


@router.get("/api/compliance/violations/{scope}")
async def list_violations(scope: str) -> dict[str, Any]:
    violations = await repo.get_violations(scope)
    summary = {"critical": 0, "warning": 0, "info": 0}
    for v in violations:
        sev = v.get("rule_severity", v.get("severity", "info"))
        summary[sev] = summary.get(sev, 0) + 1
    return {"violations": violations, "summary": summary, "total": len(violations)}


@router.post("/api/compliance/evaluate/{scope}")
async def evaluate(scope: str, request: Request) -> dict[str, Any]:
    fetcher = request.app.state.fetcher
    structured = fetcher.get_structured(scope)
    if not structured:
        raise CloudLensError(503, "Topology data not available yet")
    rules = await repo.list_compliance_rules(scope)
    violations = evaluate_rules(scope, structured, rules)
    await repo.clear_violations(scope)
    if violations:
        await repo.save_violations(violations)
    return {"violations_count": len(violations)}


@router.get("/api/compliance/recommendations/{scope}")
async def recommendations(scope: str, request: Request) -> dict[str, Any]:
    violations = await repo.get_violations(scope)
    if not violations:
        return {"recommendations": "No violations found."}
    from ai.analyzer import generate_compliance_recommendations

    recs = await generate_compliance_recommendations(violations, {}, scope)
    return {"recommendations": recs, "violations_count": len(violations)}
