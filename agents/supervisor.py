"""Supervisor Agent — orchestrates all specialist agents after each fetch cycle."""

import logging
from datetime import UTC, datetime
from typing import Any

from agents.tools import ToolExecutor

logger = logging.getLogger(__name__)


class SupervisorAgent:
    """Runs after each topology fetch. Decides which agents to invoke based on what changed."""

    def __init__(self, fetcher, registry=None):
        self._fetcher = fetcher
        self._registry = registry
        self._tool_executor = ToolExecutor(fetcher, registry)
        self._cycle = 0
        self._last_results: dict[str, Any] = {}
        self._enabled = True

        # Lazy-init agents (avoid import errors if anthropic not installed)
        self._triage = None
        self._incident = None
        self._drift = None
        self._compliance = None
        self._remediation = None

    def _init_agents(self):
        if self._triage is not None:
            return
        try:
            from agents.compliance_agent import ComplianceAgent
            from agents.drift import DriftAgent
            from agents.incident import IncidentAgent
            from agents.remediation import RemediationAgent
            from agents.triage import TriageAgent

            self._triage = TriageAgent(self._tool_executor)
            self._incident = IncidentAgent(self._tool_executor)
            self._drift = DriftAgent(self._tool_executor)
            self._compliance = ComplianceAgent(self._tool_executor)
            self._remediation = RemediationAgent(self._tool_executor)
            logger.info("Supervisor: all agents initialized")
        except Exception as e:
            logger.warning(
                "Supervisor: agent init failed (AI may not be configured): %s", e
            )
            self._enabled = False

    async def on_fetch_complete(
        self, scope: str, changes: list[dict], health_checks: list[dict]
    ) -> dict[str, Any]:
        """Called after each fetch cycle. Returns agent results."""
        if not self._enabled:
            return {"status": "disabled", "reason": "agents not initialized"}

        self._init_agents()
        if not self._enabled:
            return {"status": "disabled", "reason": "AI not configured"}

        self._cycle += 1
        results: dict[str, Any] = {
            "cycle": self._cycle,
            "timestamp": datetime.now(UTC).isoformat(),
            "scope": scope,
            "agents_run": [],
        }

        # Always: Triage
        try:
            triage_result = await self._triage.assess(changes, health_checks)
            results["triage"] = triage_result
            results["agents_run"].append("triage")
            logger.info(
                "Triage: verdict=%s changes=%d critical_health=%d",
                triage_result.get("verdict"),
                triage_result.get("changes_count", 0),
                triage_result.get("critical_health", 0),
            )
        except Exception:
            logger.exception("Triage agent failed")

        # Conditional: Incident investigation for critical events
        critical_events = [c for c in changes if c.get("severity") == "critical"]
        critical_events.extend(
            h
            for h in health_checks
            if h.get("status") == "critical" and "peering" in h.get("check_type", "")
        )

        if critical_events and self._incident:
            try:
                # Investigate the most critical event
                investigation = await self._incident.investigate(critical_events[0])
                results["incident"] = investigation
                results["agents_run"].append("incident")
                logger.info(
                    "Incident agent investigated: %s",
                    critical_events[0].get("resource_name", "?"),
                )
            except Exception:
                logger.exception("Incident agent failed")

        # Conditional: Remediation for critical health issues
        critical_health = [h for h in health_checks if h.get("status") == "critical"]
        if critical_health and self._remediation:
            try:
                remediation = await self._remediation.suggest_fixes(critical_health)
                results["remediation"] = remediation
                results["agents_run"].append("remediation")
            except Exception:
                logger.exception("Remediation agent failed")

        # Periodic: Drift analysis (every 12 cycles = ~1 hour at 300s interval)
        if self._cycle % 12 == 0 and self._drift:
            try:
                drift = await self._drift.compare_environments(scope)
                results["drift"] = drift
                results["agents_run"].append("drift")
            except Exception:
                logger.exception("Drift agent failed")

        # Periodic: Full compliance audit (every 24 cycles = ~2 hours)
        if self._cycle % 24 == 0 and self._compliance:
            try:
                audit = await self._compliance.full_audit(scope)
                results["compliance_audit"] = audit
                results["agents_run"].append("compliance")
            except Exception:
                logger.exception("Compliance agent failed")

        self._last_results = results
        logger.info(
            "Supervisor cycle %d: agents run = %s", self._cycle, results["agents_run"]
        )
        return results

    def get_last_results(self) -> dict[str, Any]:
        return self._last_results
