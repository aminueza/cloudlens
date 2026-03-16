"""Remediation Agent — generates actionable fixes (CLI commands, Terraform, PRs)."""

import logging
from typing import Any

from agents.base import BaseAgent
from agents.tools import ToolExecutor

logger = logging.getLogger(__name__)

REMEDIATION_PROMPT = """You are the Remediation Agent for CloudLens, a multi-cloud network intelligence platform.

Your job: for each issue found by other agents, generate specific, actionable fixes.

For every issue, provide:
1. **Fix command** — the exact az cli / aws cli / gcloud / terraform command
2. **Validation command** — how to verify the fix worked
3. **Rollback command** — how to undo if it breaks something
4. **Risk assessment** — what could go wrong (low/medium/high)
5. **Estimated impact** — what services are affected during the fix

Rules:
- Never suggest destructive commands without explicit warnings
- Always include rollback steps
- Prefer IaC (Terraform) over imperative CLI when possible
- Flag if the fix requires a maintenance window
- If unsure, recommend investigation rather than action

Use tools to understand the current topology and blast radius before suggesting fixes."""


class RemediationAgent(BaseAgent):
    def __init__(self, tool_executor: ToolExecutor):
        super().__init__("remediation", REMEDIATION_PROMPT, tool_executor)

    async def suggest_fixes(self, issues: list[dict[str, Any]]) -> dict[str, Any]:
        """Generate remediation plans for a list of issues."""
        issues_text = "\n".join(
            f"- [{i.get('severity', '?').upper()}] {i.get('check_type', i.get('type', '?'))}: "
            f"{i.get('message', i.get('description', '?'))}"
            for i in issues[:10]
        )

        task = (
            f"Generate remediation plans for these network issues:\n\n"
            f"{issues_text}\n\n"
            f"For each issue:\n"
            f"1. Use get_topology to understand the affected resources\n"
            f"2. Use analyze_blast_radius if the fix involves modifying critical resources\n"
            f"3. Generate the specific fix command\n"
            f"4. Include validation + rollback commands\n"
            f"5. Rate the risk of the fix"
        )

        response = await self.run(task)
        return {
            "issues_count": len(issues),
            "remediation_plan": response,
            "agent": "remediation",
        }
