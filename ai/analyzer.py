"""Claude-powered multi-cloud network analysis for CloudLens."""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from config.settings import settings

logger = logging.getLogger(__name__)

_client = None

SYSTEM_PROMPT = (
    "You are an expert cloud network SRE assistant embedded in CloudLens, "
    "an AI-powered multi-cloud network intelligence platform. You have deep "
    "knowledge of AWS VPC, Azure VNet, GCP VPC, peerings, firewalls, security "
    "groups, load balancers, gateways, and cross-cloud networking. "
    "Be concise, technical, and actionable. Use bullet points. "
    "When referencing resources, include their names, providers, and environments."
)


def _get_client():
    """Lazy-initialize the Anthropic client."""
    global _client
    if _client is None:
        try:
            import anthropic

            _client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        except Exception as e:
            logger.warning("Failed to init Anthropic client: %s", e)
            return None
    return _client


def _summarize_topology(structured: dict[str, Any]) -> str:
    """Create a compact text summary of the topology."""
    lines: list[str] = []
    stats = structured.get("stats", {})
    lines.append(
        f"Topology: {stats.get('networks', 0)} networks, "
        f"{stats.get('resources', 0)} resources, "
        f"{stats.get('peerings', 0)} peerings, "
        f"{stats.get('externalNetworks', 0)} external networks"
    )

    for v in structured.get("networks", [])[:30]:
        res_summary: dict[str, int] = {}
        for r in v.get("resources", []):
            lbl = r.get("label", r.get("resource_type", "?"))
            res_summary[lbl] = res_summary.get(lbl, 0) + 1
        sg_count = len(v.get("securityGroups", []))
        res_str = ", ".join(f"{c}x {t}" for t, c in res_summary.items())
        ext = " [EXTERNAL]" if v.get("isExternal") else ""
        provider = v.get("provider", "?").upper()
        lines.append(
            f"  [{provider}] {v.get('name', '?')} | env={v.get('env', '?')} | "
            f"region={v.get('region', '?')} | addr={','.join(v.get('addressSpace', []))} | "
            f"resources=[{res_str}] | sgs={sg_count}{ext}"
        )

    for p in structured.get("peerings", [])[:20]:
        name = p.get("name") or p.get("id", "?")
        src = p.get("sourceName", p.get("source", "?"))
        dst = p.get("targetName", p.get("target", "?"))
        # Extract VNet name from full provider ID (e.g. azure_sub_vnet-name → vnet-name)
        for prefix in ("azure_", "aws_", "gcp_"):
            if prefix in str(src):
                parts = str(src).rsplit("_", 1)
                src = parts[-1] if len(parts) > 1 else src
            if prefix in str(dst):
                parts = str(dst).rsplit("_", 1)
                dst = parts[-1] if len(parts) > 1 else dst
        lines.append(
            f"  Peering: {name} | {src} -> {dst} | state={p.get('state', '?')}"
        )

    unlinked = structured.get("unlinkedResources", [])
    if unlinked:
        lines.append(f"  Unlinked resources: {len(unlinked)}")

    return "\n".join(lines)


def _fallback_query(question: str, structured: dict[str, Any]) -> str:
    """Keyword-based fallback when AI is unavailable."""
    q = question.lower()
    stats = structured.get("stats", {})
    networks = structured.get("networks", [])
    peerings = structured.get("peerings", [])

    if any(w in q for w in ["overview", "summary", "status", "how"]):
        return (
            f"Topology: {stats.get('networks', 0)} networks, "
            f"{stats.get('resources', 0)} resources, {stats.get('peerings', 0)} peerings."
        )
    if any(w in q for w in ["peering", "peer", "connected"]):
        lines = []
        for p in peerings:
            state = p.get("state", "?")
            icon = "OK" if state in ("Connected", "active") else "FAIL"
            lines.append(f"[{icon}] {p.get('name', '?')}: {state}")
        return "\n".join(lines) or "No peerings found."
    if any(w in q for w in ["firewall", "security", "nsg"]):
        lines = []
        for v in networks:
            fw = [
                r
                for r in v.get("resources", [])
                if "firewall" in r.get("resource_type", "").lower()
            ]
            sgs = v.get("securityGroups", [])
            if fw or sgs:
                lines.append(
                    f"{v.get('name', '?')} ({v.get('env', '?')}): {len(fw)} firewalls, {len(sgs)} SGs"
                )
        return "\n".join(lines) or "No firewall/security group data."
    if any(w in q for w in ["issue", "problem", "wrong", "health"]):
        return f"Topology has {stats.get('networks', 0)} networks, {stats.get('resources', 0)} resources. Check the Health tab for detailed checks."

    return (
        f"Topology: {stats.get('networks', 0)} networks, "
        f"{stats.get('resources', 0)} resources, {stats.get('peerings', 0)} peerings.\n"
        "(AI unavailable — set ANTHROPIC_API_KEY for intelligent answers)"
    )


def _fallback_changes_analysis(changes: list[dict[str, Any]]) -> str:
    """Basic change analysis without AI."""
    if not changes:
        return "No changes detected."
    added = sum(1 for c in changes if c.get("change_type") == "added")
    removed = sum(1 for c in changes if c.get("change_type") == "removed")
    modified = sum(1 for c in changes if c.get("change_type") == "modified")
    return f"Detected {len(changes)} changes: {added} added, {removed} removed, {modified} modified."


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
    now = datetime.now(UTC).isoformat()

    # Rapid removal: more than 5 removals in last 10 changes
    recent = historical_changes[:10] if historical_changes else []
    removals = [c for c in recent if c.get("change_type") == "removed"]
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

    # Environment drift: dev has firewalls but prod doesn't
    env_firewall: dict[str, bool] = {}
    for v in current.get("networks", []):
        if v.get("isExternal"):
            continue
        env = v.get("env", "other")
        has_fw = any(
            "firewall" in r.get("resource_type", "").lower()
            for r in v.get("resources", [])
        )
        if has_fw:
            env_firewall[env] = True

    if "dev" in env_firewall and "prd" not in env_firewall:
        anomalies.append(
            {
                "type": "env_drift",
                "severity": "critical",
                "description": "Dev has firewalls but Production does not — possible configuration drift",
                "detected_at": now,
            }
        )

    # Cross-cloud drift: resource count divergence between providers
    provider_resource_counts: dict[str, int] = {}
    for v in current.get("networks", []):
        p = v.get("provider", "unknown")
        provider_resource_counts[p] = provider_resource_counts.get(p, 0) + len(
            v.get("resources", [])
        )

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
            f"- [{c.get('change_type', '?').upper()}] {c.get('resource_type', '?')}: "
            f"{c.get('resource_name', c.get('resource_id', '?'))}"
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
                now = datetime.now(UTC).isoformat()
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
