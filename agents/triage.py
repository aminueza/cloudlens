"""Triage Agent — classifies every change and health issue on each cycle."""

import logging
from typing import Any

from agents.base import BaseAgent
from agents.tools import ToolExecutor

logger = logging.getLogger(__name__)

TRIAGE_PROMPT = """You are the Triage Agent for CloudLens, a multi-cloud network intelligence platform.

Your job: after each topology poll cycle, classify every change and health issue into one of:
- IGNORE: normal operation, expected behavior
- WATCH: unusual but not urgent, log for trend analysis
- ALERT: needs attention within hours
- ESCALATE: needs immediate action, may require incident creation

You have access to tools to inspect the network topology, health checks, and blast radius.

Rules:
- Peering disconnections in production are always ESCALATE
- Firewall removals in production are always ESCALATE
- Address space overlaps are ESCALATE
- New resources in dev are usually IGNORE
- Multiple rapid removals (>3 in one cycle) are ALERT
- Security group changes in production are ALERT

Be concise. Return a structured assessment for each event."""


class TriageAgent(BaseAgent):
    def __init__(self, tool_executor: ToolExecutor):
        super().__init__("triage", TRIAGE_PROMPT, tool_executor)

    async def assess(
        self, changes: list[dict], health_checks: list[dict]
    ) -> dict[str, Any]:
        """Classify changes and health issues. Returns structured triage report."""
        critical_health = [h for h in health_checks if h.get("status") == "critical"]
        critical_changes = [c for c in changes if c.get("severity") == "critical"]

        if not changes and not critical_health:
            return {
                "verdict": "all_clear",
                "events": [],
                "summary": "No significant events",
            }

        task = (
            f"Triage these network events:\n\n"
            f"Changes ({len(changes)}):\n"
            + "\n".join(
                f"- [{c.get('change_type', '?').upper()}] {c.get('resource_type', '?')}: "
                f"{c.get('resource_name', '?')} (severity: {c.get('severity', '?')})"
                for c in changes[:20]
            )
            + f"\n\nHealth issues ({len(critical_health)} critical):\n"
            + "\n".join(
                f"- [{h.get('status', '?')}] {h.get('message', '?')}"
                for h in critical_health[:15]
            )
            + "\n\nClassify each event as IGNORE/WATCH/ALERT/ESCALATE with brief reasoning."
        )

        response = await self.run(task)

        # Determine if we need escalation
        needs_escalation = len(critical_changes) > 0 or len(critical_health) > 2
        return {
            "verdict": (
                "escalate"
                if needs_escalation
                else "alert" if critical_health else "clear"
            ),
            "changes_count": len(changes),
            "critical_health": len(critical_health),
            "critical_changes": len(critical_changes),
            "analysis": response,
        }
