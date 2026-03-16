"""AI query routes — natural language questions, history, and change summaries."""

from typing import Any

from fastapi import APIRouter, Request

from ai.analyzer import analyze_changes, query_topology
from api.models import AIQueryRequest, AIResponse
from db import repository as repo

router = APIRouter(tags=["ai"])

# In-memory conversation history (replace with DB in production)
_conversation_history: list[dict[str, str]] = []


@router.post("/api/ai/query", response_model=AIResponse)
async def ai_query(body: AIQueryRequest, request: Request) -> dict[str, Any]:
    """Answer a natural-language question about the topology."""
    fetcher = request.app.state.fetcher
    scope = body.scope or "all"
    structured = fetcher.get_structured(scope) or {"providers": {}}
    changes = await repo.get_changes(scope)

    from engine.health import run_health_checks

    health = run_health_checks(structured, scope)

    answer = await query_topology(
        question=body.question,
        structured=structured,
        scope=scope,
        health_checks=health,
        changes=changes,
        conversation_history=_conversation_history[-20:],
    )

    # Store in conversation history
    _conversation_history.append({"role": "user", "content": body.question})
    _conversation_history.append({"role": "assistant", "content": answer})

    return {"response": answer, "scope": scope}


@router.get("/api/ai/history")
async def ai_history(request: Request) -> dict[str, Any]:
    """Return conversation history."""
    return {"history": _conversation_history}


@router.post("/api/ai/summarize-changes", response_model=AIResponse)
async def summarize_changes(body: AIQueryRequest, request: Request) -> dict[str, Any]:
    """AI-powered change summary."""
    fetcher = request.app.state.fetcher
    scope = body.scope or "all"
    structured = fetcher.get_structured(scope) or {"providers": {}}
    changes = await repo.get_changes(scope)

    analysis = await analyze_changes(changes, structured, scope)
    return {"response": analysis, "scope": scope}
