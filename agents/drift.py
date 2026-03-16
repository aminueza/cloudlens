"""Drift Agent — compares environments and cross-cloud, finds divergences."""

import logging
from typing import Any

from agents.base import BaseAgent
from agents.tools import ToolExecutor

logger = logging.getLogger(__name__)

DRIFT_PROMPT = """You are the Drift Agent for CloudLens, a multi-cloud network intelligence platform.

Your job: periodically compare environments (dev/stg/prd) and cross-cloud deployments
to find configuration drift that humans miss.

Use the compare_environments tool to get environment comparison data, then analyze:
1. Resources in dev but not prod (features not promoted?)
2. Resources in prod but not dev (manual changes? shadow IT?)
3. Security posture gaps (prod missing firewalls that dev has)
4. Network topology differences (different peering patterns)
5. Address space inconsistencies

Flag anything that looks unintentional. Not all drift is bad — dev having
fewer resources than prod is normal. But prod having LESS security than dev is a red flag."""


class DriftAgent(BaseAgent):
    def __init__(self, tool_executor: ToolExecutor):
        super().__init__("drift", DRIFT_PROMPT, tool_executor)

    async def compare_environments(self, scope: str = "all") -> dict[str, Any]:
        """Compare dev vs prd environments for drift."""
        task = (
            f"Compare the dev and prd environments for scope '{scope}'.\n\n"
            f"Use the compare_environments tool, then analyze the differences.\n"
            f"Use get_topology to understand the full picture.\n"
            f"Use run_health_checks to see if there are environment-specific health issues.\n\n"
            f"Report:\n"
            f"1. What's in dev but not prod\n"
            f"2. What's in prod but not dev\n"
            f"3. Security posture differences\n"
            f"4. Any concerning drift patterns"
        )

        response = await self.run(task)
        return {"scope": scope, "analysis": response, "agent": "drift"}
