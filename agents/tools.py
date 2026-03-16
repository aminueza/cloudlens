"""Tool definitions and executor for Claude tool_use — wraps existing engines."""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


TOOL_DEFINITIONS = [
    {
        "name": "get_topology",
        "description": "Get current network topology for a scope (product name or 'all'). Returns networks, peerings, stats.",
        "input_schema": {
            "type": "object",
            "properties": {
                "scope": {
                    "type": "string",
                    "description": "Product name or 'all'",
                    "default": "all",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_changes",
        "description": "Get recent topology changes. Returns list of added/removed/modified resources with severity.",
        "input_schema": {
            "type": "object",
            "properties": {
                "scope": {"type": "string", "default": "all"},
                "limit": {"type": "integer", "default": 50},
            },
            "required": [],
        },
    },
    {
        "name": "run_health_checks",
        "description": "Run health checks on current topology. Returns list of issues with severity (critical/warning/healthy).",
        "input_schema": {
            "type": "object",
            "properties": {"scope": {"type": "string", "default": "all"}},
            "required": [],
        },
    },
    {
        "name": "analyze_blast_radius",
        "description": "Analyze impact if a specific resource goes down. Traces peering chains, finds affected resources.",
        "input_schema": {
            "type": "object",
            "properties": {"resource_id": {"type": "string"}},
            "required": ["resource_id"],
        },
    },
    {
        "name": "get_compliance_violations",
        "description": "Get current compliance rule violations for a scope.",
        "input_schema": {
            "type": "object",
            "properties": {"scope": {"type": "string", "default": "all"}},
            "required": [],
        },
    },
    {
        "name": "search_past_incidents",
        "description": "Search historical incidents for similar patterns.",
        "input_schema": {
            "type": "object",
            "properties": {
                "scope": {"type": "string", "default": "all"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": [],
        },
    },
    {
        "name": "create_incident",
        "description": "Create a new incident with auto-enrichment. Returns incident ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "severity": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "critical"],
                },
                "scope": {"type": "string", "default": "all"},
                "description": {"type": "string", "default": ""},
            },
            "required": ["title", "severity"],
        },
    },
    {
        "name": "add_incident_annotation",
        "description": "Add a note/annotation to an existing incident.",
        "input_schema": {
            "type": "object",
            "properties": {
                "incident_id": {"type": "integer"},
                "content": {"type": "string"},
                "author": {"type": "string", "default": "agent"},
            },
            "required": ["incident_id", "content"],
        },
    },
    {
        "name": "get_dependency_graph",
        "description": "Get the full dependency graph with critical nodes (single points of failure) identified via Tarjan's algorithm.",
        "input_schema": {
            "type": "object",
            "properties": {"scope": {"type": "string", "default": "all"}},
            "required": [],
        },
    },
    {
        "name": "compare_environments",
        "description": "Compare network topology between two environments (e.g., dev vs prd) for a product.",
        "input_schema": {
            "type": "object",
            "properties": {
                "scope": {"type": "string"},
                "env_a": {"type": "string", "default": "dev"},
                "env_b": {"type": "string", "default": "prd"},
            },
            "required": ["scope"],
        },
    },
]


class ToolExecutor:
    """Executes tool calls against CloudLens engines and DB."""

    def __init__(self, fetcher, registry=None):
        self._fetcher = fetcher
        self._registry = registry

    async def execute(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        """Execute a tool and return JSON result string."""
        try:
            handler = getattr(self, f"_tool_{tool_name}", None)
            if not handler:
                return json.dumps({"error": f"Unknown tool: {tool_name}"})
            result = await handler(tool_input)
            return json.dumps(result, default=str)
        except Exception as e:
            logger.warning("Tool %s failed: %s", tool_name, e)
            return json.dumps({"error": str(e)})

    async def _tool_get_topology(self, inp: dict) -> dict:
        scope = inp.get("scope", "all")
        data = self._fetcher.get_structured(scope)
        if not data:
            return {"error": "No topology data available"}
        stats = data.get("stats", {})
        networks = [
            {
                "name": n.get("name"),
                "env": n.get("env"),
                "provider": n.get("provider"),
                "region": n.get("region"),
                "addressSpace": n.get("addressSpace"),
                "resources": len(n.get("resources", [])),
                "securityGroups": len(n.get("securityGroups", [])),
            }
            for n in data.get("networks", [])[:50]
        ]
        peerings = [
            {
                "name": p.get("name"),
                "state": p.get("state"),
                "source": p.get("sourceName"),
                "target": p.get("targetName"),
            }
            for p in data.get("peerings", [])[:30]
        ]
        return {"stats": stats, "networks": networks, "peerings": peerings}

    async def _tool_get_changes(self, inp: dict) -> dict:
        from db import repository as repo

        scope = inp.get("scope", "all")
        limit = inp.get("limit", 50)
        changes = await repo.get_changes(scope, limit=limit)
        summary = await repo.get_change_summary(scope)
        return {"changes": changes[:20], "summary": summary, "total": len(changes)}

    async def _tool_run_health_checks(self, inp: dict) -> dict:
        from engine.health import compute_health_score, run_health_checks

        scope = inp.get("scope", "all")
        structured = self._fetcher.get_structured(scope)
        if not structured:
            return {"error": "No topology data"}
        checks = run_health_checks(scope, structured)
        score = compute_health_score(checks)
        critical = [c for c in checks if c.get("status") == "critical"]
        warnings = [c for c in checks if c.get("status") == "warning"]
        return {
            "score": score,
            "critical": [
                {
                    "check_type": c.get("check_type"),
                    "message": c.get("message"),
                    "resource_name": c.get("resource_name"),
                }
                for c in critical
            ],
            "warnings_count": len(warnings),
            "total_checks": len(checks),
        }

    async def _tool_analyze_blast_radius(self, inp: dict) -> dict:
        from engine.blast_radius import analyze_blast_radius

        structured = self._fetcher.get_structured("all")
        if not structured:
            return {"error": "No topology data"}
        return analyze_blast_radius(inp["resource_id"], structured)

    async def _tool_get_compliance_violations(self, inp: dict) -> dict:
        from db import repository as repo

        scope = inp.get("scope", "all")
        violations = await repo.get_violations(scope)
        return {"violations": violations[:20], "total": len(violations)}

    async def _tool_search_past_incidents(self, inp: dict) -> dict:
        from db import repository as repo

        scope = inp.get("scope", "all")
        incidents = await repo.list_incidents(scope=scope, limit=inp.get("limit", 10))
        return {"incidents": incidents}

    async def _tool_create_incident(self, inp: dict) -> dict:
        from db import repository as repo

        incident_id = await repo.create_incident(
            scope=inp.get("scope", "all"),
            title=inp["title"],
            severity=inp["severity"],
            description=inp.get("description", ""),
        )
        await repo.add_annotation(
            incident_id, f"Auto-created by agent: {inp['title']}", author="agent"
        )
        return {"incident_id": incident_id, "status": "created"}

    async def _tool_add_incident_annotation(self, inp: dict) -> dict:
        from db import repository as repo

        await repo.add_annotation(
            inp["incident_id"],
            inp["content"],
            author=inp.get("author", "agent"),
        )
        return {"status": "added"}

    async def _tool_get_dependency_graph(self, inp: dict) -> dict:
        from engine.blast_radius import get_dependency_graph

        structured = self._fetcher.get_structured(inp.get("scope", "all"))
        if not structured:
            return {"error": "No topology data"}
        dep = get_dependency_graph(structured)
        return {
            "total_nodes": dep.get("total_nodes"),
            "total_edges": dep.get("total_edges"),
            "critical_nodes": dep.get("critical_nodes", []),
        }

    async def _tool_compare_environments(self, inp: dict) -> dict:
        scope = inp.get("scope", "all")
        env_a = inp.get("env_a", "dev")
        env_b = inp.get("env_b", "prd")
        structured = self._fetcher.get_structured(scope)
        if not structured:
            return {"error": "No topology data"}

        nets_a = [n for n in structured.get("networks", []) if n.get("env") == env_a]
        nets_b = [n for n in structured.get("networks", []) if n.get("env") == env_b]
        names_a = {n.get("name", "").replace(f"-{env_a}", "") for n in nets_a}
        names_b = {n.get("name", "").replace(f"-{env_b}", "") for n in nets_b}

        return {
            f"{env_a}_only": list(names_a - names_b),
            f"{env_b}_only": list(names_b - names_a),
            "both": list(names_a & names_b),
            f"{env_a}_count": len(nets_a),
            f"{env_b}_count": len(nets_b),
            f"{env_a}_resources": sum(len(n.get("resources", [])) for n in nets_a),
            f"{env_b}_resources": sum(len(n.get("resources", [])) for n in nets_b),
        }
