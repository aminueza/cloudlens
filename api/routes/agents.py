"""Agent API routes — status, results, and manual triggers."""

from typing import Any

from fastapi import APIRouter, Request

from api.errors import CloudLensError

router = APIRouter(tags=["agents"])


@router.get("/api/agents/status")
async def agent_status(request: Request) -> dict[str, Any]:
    """Get latest agent supervisor results."""
    fetcher = request.app.state.fetcher
    results = fetcher.get_supervisor_results()
    if not results:
        return {
            "status": "no_results",
            "message": "Agents haven't run yet. Wait for the next fetch cycle.",
        }
    return results


@router.post("/api/agents/run")
async def trigger_agents(request: Request, scope: str = "all") -> dict[str, Any]:
    """Manually trigger agent analysis on current topology."""
    fetcher = request.app.state.fetcher
    structured = fetcher.get_structured(scope)
    if not structured:
        raise CloudLensError(503, "No topology data available")

    supervisor = fetcher._supervisor
    if not supervisor:
        raise CloudLensError(
            503, "Agent supervisor not initialized (set ANTHROPIC_API_KEY)"
        )

    from db import repository as repo
    from engine.health import run_health_checks

    changes = await repo.get_changes(scope, limit=50)
    health = run_health_checks(scope, structured)

    results = await supervisor.on_fetch_complete(scope, changes, health)
    return results


@router.post("/api/agents/investigate")
async def trigger_investigation(request: Request, scope: str = "all") -> dict[str, Any]:
    """Manually trigger incident investigation on critical issues."""
    fetcher = request.app.state.fetcher
    structured = fetcher.get_structured(scope)
    if not structured:
        raise CloudLensError(503, "No topology data available")

    from agents.incident import IncidentAgent
    from agents.tools import ToolExecutor
    from engine.health import run_health_checks

    health = run_health_checks(scope, structured)
    critical = [h for h in health if h.get("status") == "critical"]
    if not critical:
        return {
            "status": "no_critical_issues",
            "message": "No critical issues to investigate",
        }

    executor = ToolExecutor(fetcher, request.app.state.registry)
    agent = IncidentAgent(executor)
    result = await agent.investigate(critical[0])
    return result


@router.post("/api/agents/audit")
async def trigger_audit(request: Request, scope: str = "all") -> dict[str, Any]:
    """Manually trigger AI compliance audit."""
    fetcher = request.app.state.fetcher
    if not fetcher.get_structured(scope):
        raise CloudLensError(503, "No topology data available")

    from agents.compliance_agent import ComplianceAgent
    from agents.tools import ToolExecutor

    executor = ToolExecutor(fetcher, request.app.state.registry)
    agent = ComplianceAgent(executor)
    return await agent.full_audit(scope)


@router.post("/api/agents/drift")
async def trigger_drift(request: Request, scope: str = "all") -> dict[str, Any]:
    """Manually trigger environment drift analysis."""
    fetcher = request.app.state.fetcher
    if not fetcher.get_structured(scope):
        raise CloudLensError(503, "No topology data available")

    from agents.drift import DriftAgent
    from agents.tools import ToolExecutor

    executor = ToolExecutor(fetcher, request.app.state.registry)
    agent = DriftAgent(executor)
    return await agent.compare_environments(scope)
