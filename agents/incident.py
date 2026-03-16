"""Incident Agent — auto-creates incidents, investigates root cause, proposes remediation."""

import logging
from typing import Any

from agents.base import BaseAgent
from agents.tools import ToolExecutor

logger = logging.getLogger(__name__)

INCIDENT_PROMPT = """You are the Incident Agent for CloudLens, a multi-cloud network intelligence platform.

Your job: when critical events occur, you autonomously investigate and create incidents.

Process:
1. Use get_topology to understand current network state
2. Use analyze_blast_radius on affected resources to understand impact
3. Use get_changes to find what changed recently
4. Use search_past_incidents to find similar historical events
5. Use create_incident to create a tracked incident
6. Use add_incident_annotation to document your findings

Your investigation should determine:
- What happened (the change/failure)
- Why it matters (blast radius, affected services)
- Most likely root cause
- Whether this has happened before
- Recommended immediate actions
- Recommended prevention measures

Be thorough but concise. Use tools to gather evidence before concluding."""


class IncidentAgent(BaseAgent):
    def __init__(self, tool_executor: ToolExecutor):
        super().__init__("incident", INCIDENT_PROMPT, tool_executor)

    async def investigate(self, trigger: dict[str, Any]) -> dict[str, Any]:
        """Auto-investigate a critical event. Creates incident and documents findings."""
        trigger_type = trigger.get("change_type", trigger.get("check_type", "unknown"))
        resource = trigger.get("resource_name", trigger.get("message", "unknown"))
        severity = trigger.get("severity", "critical")

        task = (
            f"A critical network event requires investigation:\n\n"
            f"Event type: {trigger_type}\n"
            f"Resource: {resource}\n"
            f"Severity: {severity}\n"
            f"Details: {trigger}\n\n"
            f"Investigate this event:\n"
            f"1. Check the current topology state\n"
            f"2. Analyze blast radius for affected resources\n"
            f"3. Look at recent changes for correlation\n"
            f"4. Search past incidents for similar events\n"
            f"5. Create an incident to track this\n"
            f"6. Document your root cause analysis as an incident annotation\n\n"
            f"Provide your full investigation report."
        )

        response = await self.run(task)

        return {
            "trigger": trigger,
            "investigation": response,
            "agent": "incident",
        }
