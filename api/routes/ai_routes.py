"""AI query routes — natural language questions, history, and change summaries."""

from typing import Any

from fastapi import APIRouter, Request

from ai.analyzer import analyze_changes, query_topology
from api.models import AIQueryRequest
from db import repository as repo

router = APIRouter(tags=["ai"])


@router.post("/api/ai/query")
async def ai_query(body: AIQueryRequest, request: Request) -> dict[str, Any]:
    """Answer a natural-language question about the topology."""
    fetcher = request.app.state.fetcher
    scope = body.scope or "all"
    structured = fetcher.get_structured(scope) or {}

    changes = await repo.get_changes(scope)

    from engine.health import run_health_checks

    health = run_health_checks(scope, structured)

    raw_history = await repo.get_ai_history(scope, limit=20)
    history = [{"role": m["role"], "content": m["content"]} for m in raw_history if "role" in m and "content" in m]

    await repo.save_ai_message(scope, "user", body.question)

    answer = await query_topology(
        question=body.question,
        structured=structured,
        scope=scope,
        health_checks=health,
        changes=changes,
        conversation_history=history,
    )

    await repo.save_ai_message(scope, "assistant", answer)

    return {"answer": answer, "scope": scope}


@router.get("/api/ai/history")
async def ai_history(scope: str = "all") -> dict[str, Any]:
    messages = await repo.get_ai_history(scope, limit=50)
    return {"messages": messages}


@router.post("/api/ai/summarize-changes")
async def summarize_changes(body: AIQueryRequest, request: Request) -> dict[str, Any]:
    fetcher = request.app.state.fetcher
    scope = body.scope or "all"
    structured = fetcher.get_structured(scope) or {}
    changes = await repo.get_changes(scope)

    analysis = await analyze_changes(changes, structured, scope)

    critical = sum(1 for c in changes if c.get("severity") == "critical")
    risk = "critical" if critical > 0 else "warning" if len(changes) > 5 else "low"

    return {"summary": analysis, "risk": risk, "changes_count": len(changes)}
