"""Compliance Agent — AI-powered audit beyond static rules."""

import logging
from typing import Any

from agents.base import BaseAgent
from agents.tools import ToolExecutor

logger = logging.getLogger(__name__)

COMPLIANCE_PROMPT = """You are the Compliance Agent for CloudLens, a multi-cloud network intelligence platform.

Your job: perform deep compliance audits that go beyond static rules. Static rules catch
known patterns, but you look for intent violations and contextual issues.

Look for:
- Public IPs on resources that shouldn't be internet-facing
- Networks with no egress filtering (no firewall, no NAT gateway)
- Cross-environment connectivity that shouldn't exist (dev peered to prod)
- Overly permissive security groups (0 rules = allow-all default)
- Resources in unexpected regions (data residency violations)
- Single points of failure with no redundancy
- Naming convention violations suggesting shadow IT or manual provisioning
- Production resources without proper tagging

Use tools to inspect topology, compliance violations, health checks, and dependencies.
Provide prioritized findings with remediation suggestions."""


class ComplianceAgent(BaseAgent):
    def __init__(self, tool_executor: ToolExecutor):
        super().__init__("compliance", COMPLIANCE_PROMPT, tool_executor)

    async def full_audit(self, scope: str = "all") -> dict[str, Any]:
        """Run a comprehensive AI-powered compliance audit."""
        task = (
            f"Perform a full compliance audit for scope '{scope}'.\n\n"
            f"Steps:\n"
            f"1. Use get_topology to see the full network state\n"
            f"2. Use get_compliance_violations to see known rule violations\n"
            f"3. Use run_health_checks to see infrastructure health\n"
            f"4. Use get_dependency_graph to find single points of failure\n"
            f"5. Use compare_environments to check dev/prod parity\n\n"
            f"Go beyond the static rules. Find issues that rules can't express.\n"
            f"Prioritize findings as: CRITICAL / HIGH / MEDIUM / LOW\n"
            f"For each finding, suggest the specific fix."
        )

        response = await self.run(task)
        return {"scope": scope, "audit": response, "agent": "compliance"}
