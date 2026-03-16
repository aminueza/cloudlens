"""Claude-powered multi-cloud network analysis for CloudLens."""

import asyncio
import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Any

import anthropic

from config.settings import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are an expert cloud network SRE assistant embedded in CloudLens, "
    "an AI-powered multi-cloud network intelligence platform. You have deep "
    "knowledge of AWS VPC, Azure VNet, GCP VPC, peerings, firewalls, security "
    "groups, load balancers, gateways, and cross-cloud networking."
)

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    """Lazy-initialize the Anthropic client."""
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


def _summarize_topology(structured: dict[str, Any]) -> str:
    """Create a compact text summary of the topology with provider labels."""
    lines: list[str] = []
    providers = structured.get("providers", {})
    for provider_name, provider_data in providers.items():
        resources = provider_data.get("resources", [])
        lines.append(f"[{provider_name.upper()}] {len(resources)} resources")
        type_counts: Counter[str] = Counter()
        for r in resources:
            type_counts[r.get("type", "unknown")] += 1
        for rtype, count in type_counts.most_common(10):
            lines.append(f"  - {rtype}: {count}")
        connections = provider_data.get("connections", [])
        if connections:
            lines.append(f"  - connections: {len(connections)}")

    cross_cloud = structured.get("cross_cloud_connections", [])
    if cross_cloud:
        lines.append(f"[CROSS-CLOUD] {len(cross_cloud)} peerings/connections")

    nodes = structured.get("nodes", [])
    edges = structured.get("edges", [])
    if nodes:
        lines.append(f"Total nodes: {len(nodes)}")
    if edges:
        lines.append(f"Total edges: {len(edges)}")

    return "\n".join(lines) if lines else "Empty topology"


def _fallback_query(question: str, structured: dict[str, Any]) -> str:
    """Keyword-based fallback when AI is unavailable."""
    q = question.lower()
    summary = _summarize_topology(structured)
    nodes = structured.get("nodes", [])
    edges = structured.get("edges", [])

    if "how many" in q and ("resource" in q or "node" in q):
        return f"There are {len(nodes)} resources in the topology."
    if "how many" in q and ("connection" in q or "edge" in q):
        return f"There are {len(edges)} connections in the topology."
    if "vpc" in q or "vnet" in q:
        vpcs = [n for n in nodes if n.get("type", "").lower() in ("vpc", "vnet")]
        return f"Found {len(vpcs)} VPC/VNet resources."
    if "firewall" in q or "security group" in q or "nsg" in q:
        fws = [
            n
            for n in nodes
            if "firewall" in n.get("type", "").lower()
            or "security" in n.get("type", "").lower()
        ]
        return f"Found {len(fws)} firewall/security group resources."
    return f"AI analysis is currently unavailable. Topology summary:\n{summary}"


def _fallback_changes_analysis(changes: list[dict[str, Any]]) -> str:
    """Basic change analysis without AI."""
    if not changes:
        return "No changes detected."
    added = sum(1 for c in changes if c.get("action") == "added")
    removed = sum(1 for c in changes if c.get("action") == "removed")
    modified = sum(1 for c in changes if c.get("action") == "modified")
    return (
        f"Detected {len(changes)} changes: {added} added, "
        f"{removed} removed, {modified} modified."
    )


def _fallback_incident_analysis(incident: dict[str, Any]) -> str:
    """Basic incident analysis without AI."""
    severity = incident.get("severity", "unknown")
    title = incident.get("title", "Unknown incident")
    return (
        f"Incident: {title} (severity: {severity}). "
        "AI root-cause analysis unavailable. Review recent changes and health checks."
    )


def _fallback_compliance_recommendations(violations: list[dict[str, Any]]) -> str:
    """Basic compliance recommendations without AI."""
    if not violations:
        return "No compliance violations found."
    lines = [f"Found {len(violations)} violations:"]
    for v in violations[:10]:
        lines.append(
            f"  - {v.get('rule_name', 'unknown')}: {v.get('resource_id', 'N/A')}"
        )
    lines.append(
        "Review each violation and remediate according to your security policy."
    )
    return "\n".join(lines)


def _rule_based_anomalies(
    current: dict[str, Any],
    historical_changes: list[dict[str, Any]],
    scope: str,
) -> list[dict[str, Any]]:
    """Rule-based anomaly detection."""
    anomalies: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat()

    # Rapid removal: more than 5 removals in last 10 changes
    recent = historical_changes[:10] if historical_changes else []
    removals = [c for c in recent if c.get("action") == "removed"]
    if len(removals) > 5:
        anomalies.append(
            {
                "type": "rapid_removal",
                "severity": "high",
                "description": (
                    f"{len(removals)} resources removed in the last "
                    f"{len(recent)} changes — possible misconfiguration or attack."
                ),
                "detected_at": now,
            }
        )

    # Environment drift: dev has firewalls but prod doesn't (or vice versa)
    providers = current.get("providers", {})
    env_firewall_counts: dict[str, int] = {}
    for provider_name, pdata in providers.items():
        for r in pdata.get("resources", []):
            env = r.get("environment", r.get("env", "unknown"))
            rtype = r.get("type", "").lower()
            if "firewall" in rtype or "security" in rtype or "nsg" in rtype:
                env_firewall_counts[env] = env_firewall_counts.get(env, 0) + 1

    if "dev" in env_firewall_counts and "prod" not in env_firewall_counts:
        anomalies.append(
            {
                "type": "env_drift",
                "severity": "medium",
                "description": (
                    "Dev environment has firewall rules but prod does not. "
                    "This may indicate a security gap in production."
                ),
                "detected_at": now,
            }
        )
    elif "prod" in env_firewall_counts and "dev" not in env_firewall_counts:
        anomalies.append(
            {
                "type": "env_drift",
                "severity": "low",
                "description": (
                    "Prod has firewall rules but dev does not. "
                    "Dev environment may be under-secured."
                ),
                "detected_at": now,
            }
        )

    # Cross-cloud drift: resource count divergence between providers
    provider_resource_counts: dict[str, int] = {}
    for provider_name, pdata in providers.items():
        provider_resource_counts[provider_name] = len(pdata.get("resources", []))

    if len(provider_resource_counts) >= 2:
        counts = list(provider_resource_counts.values())
        max_count = max(counts)
        min_count = min(counts)
        if max_count > 0 and min_count > 0 and max_count / min_count > 3:
            max_provider = max(provider_resource_counts, key=provider_resource_counts.get)  # type: ignore[arg-type]
            min_provider = min(provider_resource_counts, key=provider_resource_counts.get)  # type: ignore[arg-type]
            anomalies.append(
                {
                    "type": "cross_cloud_drift",
                    "severity": "medium",
                    "description": (
                        f"Significant resource count divergence: {max_provider} has "
                        f"{provider_resource_counts[max_provider]} resources vs "
                        f"{min_provider} with {provider_resource_counts[min_provider]}."
                    ),
                    "detected_at": now,
                }
            )

    return anomalies


async def query_topology(
    question: str,
    structured: dict[str, Any],
    scope: str = "all",
    health_checks: list[dict[str, Any]] | None = None,
    changes: list[dict[str, Any]] | None = None,
    conversation_history: list[dict[str, str]] | None = None,
) -> str:
    """Answer a natural-language question about the topology."""
    try:
        client = _get_client()
        topo_summary = _summarize_topology(structured)

        context_parts = [f"Current topology ({scope}):\n{topo_summary}"]
        if health_checks:
            context_parts.append(
                f"Health checks: {len(health_checks)} total, "
                f"{sum(1 for h in health_checks if h.get('status') == 'critical')} critical"
            )
        if changes:
            context_parts.append(f"Recent changes: {len(changes)}")

        messages: list[dict[str, str]] = []
        if conversation_history:
            messages.extend(conversation_history)
        messages.append(
            {
                "role": "user",
                "content": f"{chr(10).join(context_parts)}\n\nQuestion: {question}",
            }
        )

        response = await asyncio.to_thread(
            client.messages.create,
            model=settings.AI_MODEL,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
        return str(response.content[0].text)
    except Exception:
        logger.warning(
            "AI unavailable for topology query, using fallback", exc_info=True
        )
        return _fallback_query(question, structured)


async def analyze_changes(
    changes: list[dict[str, Any]],
    structured: dict[str, Any],
    scope: str = "all",
) -> str:
    """Analyze recent topology changes."""
    try:
        client = _get_client()
        topo_summary = _summarize_topology(structured)
        changes_text = "\n".join(
            f"- {c.get('action', '?')} {c.get('resource_type', '?')} "
            f"{c.get('resource_id', '?')} ({c.get('provider', '?')})"
            for c in changes[:50]
        )

        prompt = (
            f"Topology ({scope}):\n{topo_summary}\n\n"
            f"Recent changes:\n{changes_text}\n\n"
            "Analyze these changes. Highlight risks, security implications, "
            "and any patterns you see. Be concise."
        )

        response = await asyncio.to_thread(
            client.messages.create,
            model=settings.AI_MODEL,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return str(response.content[0].text)
    except Exception:
        logger.warning(
            "AI unavailable for change analysis, using fallback", exc_info=True
        )
        return _fallback_changes_analysis(changes)


async def analyze_incident(
    incident: dict[str, Any],
    structured: dict[str, Any],
    changes: list[dict[str, Any]] | None = None,
    health_checks: list[dict[str, Any]] | None = None,
) -> str:
    """Perform AI-powered root cause analysis for an incident."""
    try:
        client = _get_client()
        topo_summary = _summarize_topology(structured)

        context_parts = [
            f"Incident: {incident.get('title', 'Unknown')}",
            f"Severity: {incident.get('severity', 'unknown')}",
            f"Description: {incident.get('description', 'N/A')}",
            f"Scope: {incident.get('scope', 'all')}",
            f"\nTopology:\n{topo_summary}",
        ]
        if changes:
            changes_text = "\n".join(
                f"- {c.get('action')} {c.get('resource_type')} {c.get('resource_id')}"
                for c in changes[:30]
            )
            context_parts.append(f"\nRecent changes:\n{changes_text}")
        if health_checks:
            failing = [
                h for h in health_checks if h.get("status") in ("critical", "warning")
            ]
            if failing:
                health_text = "\n".join(
                    f"- {h.get('check_name')}: {h.get('status')} - {h.get('message', '')}"
                    for h in failing[:20]
                )
                context_parts.append(f"\nFailing health checks:\n{health_text}")

        prompt = (
            "\n".join(context_parts) + "\n\n"
            "Perform root cause analysis. Identify likely causes, correlate "
            "with recent changes, and suggest remediation steps."
        )

        response = await asyncio.to_thread(
            client.messages.create,
            model=settings.AI_MODEL,
            max_tokens=3000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return str(response.content[0].text)
    except Exception:
        logger.warning(
            "AI unavailable for incident analysis, using fallback", exc_info=True
        )
        return _fallback_incident_analysis(incident)


async def generate_compliance_recommendations(
    violations: list[dict[str, Any]],
    structured: dict[str, Any],
    scope: str = "all",
) -> str:
    """Generate AI-powered compliance remediation recommendations."""
    try:
        client = _get_client()
        topo_summary = _summarize_topology(structured)
        violations_text = "\n".join(
            f"- [{v.get('severity', '?')}] {v.get('rule_name', '?')}: "
            f"{v.get('resource_id', '?')} ({v.get('provider', '?')}) - {v.get('message', '')}"
            for v in violations[:30]
        )

        prompt = (
            f"Topology ({scope}):\n{topo_summary}\n\n"
            f"Compliance violations:\n{violations_text}\n\n"
            "Provide prioritized remediation recommendations. Group by severity "
            "and provider. Include specific actions for each violation type."
        )

        response = await asyncio.to_thread(
            client.messages.create,
            model=settings.AI_MODEL,
            max_tokens=3000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return str(response.content[0].text)
    except Exception:
        logger.warning(
            "AI unavailable for compliance recommendations, using fallback",
            exc_info=True,
        )
        return _fallback_compliance_recommendations(violations)


async def detect_anomalies(
    current: dict[str, Any],
    historical_changes: list[dict[str, Any]],
    scope: str = "all",
) -> list[dict[str, Any]]:
    """Detect anomalies using rule-based checks and optional AI enhancement."""
    rule_anomalies = _rule_based_anomalies(current, historical_changes, scope)

    try:
        client = _get_client()
        topo_summary = _summarize_topology(current)
        changes_text = "\n".join(
            f"- {c.get('action')} {c.get('resource_type')} {c.get('resource_id')}"
            for c in historical_changes[:30]
        )

        prompt = (
            f"Topology ({scope}):\n{topo_summary}\n\n"
            f"Recent changes:\n{changes_text}\n\n"
            f"Rule-based anomalies already detected: {len(rule_anomalies)}\n"
            "Identify any additional anomalies or patterns that might indicate "
            "issues. Return a JSON array of objects with keys: type, severity, description. "
            "Only return NEW anomalies not already covered by the rule-based ones."
        )

        response = await asyncio.to_thread(
            client.messages.create,
            model=settings.AI_MODEL,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        ai_text = str(response.content[0].text)

        # Try to parse AI response as JSON list
        import json

        try:
            # Extract JSON from response (may be wrapped in markdown)
            start = ai_text.find("[")
            end = ai_text.rfind("]") + 1
            if start >= 0 and end > start:
                ai_anomalies = json.loads(ai_text[start:end])
                now = datetime.now(timezone.utc).isoformat()
                for a in ai_anomalies:
                    a.setdefault("detected_at", now)
                    a.setdefault("severity", "low")
                rule_anomalies.extend(ai_anomalies)
        except (json.JSONDecodeError, ValueError):
            logger.debug("Could not parse AI anomaly response as JSON")

    except Exception:
        logger.warning(
            "AI unavailable for anomaly detection, using rule-based only", exc_info=True
        )

    return rule_anomalies
