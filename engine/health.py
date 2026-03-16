"""Health check engine — analyzes topology for issues and anomalies."""

import ipaddress
import logging

logger = logging.getLogger(__name__)


def run_health_checks(product: str, structured: dict) -> list[dict]:
    """Run all health checks against topology data. Returns list of health check results."""
    checks = []
    checks.extend(_check_peering_state(product, structured))
    checks.extend(_check_empty_sgs(product, structured))
    checks.extend(_check_orphaned_resources(product, structured))
    checks.extend(_check_address_overlap(product, structured))
    checks.extend(_check_missing_critical_resources(product, structured))
    checks.extend(_check_vnet_isolation(product, structured))
    checks.extend(_check_provisioning_state(product, structured))
    return checks


def _check_peering_state(product: str, data: dict) -> list[dict]:
    """Flag peerings that are not in connected/active state."""
    results = []
    connected_states = {"connected", "active"}
    for p in data.get("peerings", []):
        state = (p.get("state") or "unknown").lower()
        if state not in connected_states:
            results.append(
                {
                    "product": product,
                    "check_type": "peering_disconnected",
                    "status": "critical",
                    "resource_type": "peering",
                    "resource_id": p.get("id", ""),
                    "resource_name": p.get("name", "unknown"),
                    "message": f"Network peering '{p.get('name')}' state: {state} (expected: connected)",
                    "details": {
                        "state": state,
                        "from": p.get("source_network", p.get("fromId", "")),
                        "to": p.get("target_network", p.get("toId", "")),
                    },
                }
            )
    if not any(r["check_type"] == "peering_disconnected" for r in results):
        total = len(data.get("peerings", []))
        if total > 0:
            results.append(
                {
                    "product": product,
                    "check_type": "peering_disconnected",
                    "status": "healthy",
                    "message": f"All {total} peerings are connected",
                }
            )
    return results


def _check_empty_sgs(product: str, data: dict) -> list[dict]:
    """Flag Security Groups with zero rules."""
    results = []
    for v in data.get("networks", []):
        for sg in v.get("securityGroups", []):
            if sg.get("rules", 0) == 0:
                results.append(
                    {
                        "product": product,
                        "check_type": "empty_sg",
                        "status": "warning",
                        "resource_type": "sg",
                        "resource_id": sg.get("id", ""),
                        "resource_name": sg.get("name", ""),
                        "message": f"Security Group '{sg['name']}' in Network '{v['name']}' has 0 security rules",
                        "details": {"vnet": v["name"], "env": v.get("env", "")},
                    }
                )
    return results


def _check_orphaned_resources(product: str, data: dict) -> list[dict]:
    """Flag resources not linked to any Network."""
    results = []
    for r in data.get("unlinkedResources", []):
        results.append(
            {
                "product": product,
                "check_type": "orphaned_resource",
                "status": "warning",
                "resource_type": r.get("type", r.get("label", "resource")),
                "resource_id": r.get("id", ""),
                "resource_name": r.get("name", ""),
                "message": f"Resource '{r['name']}' ({r.get('label', '')}) is not linked to any Network",
                "details": {
                    "type": r.get("label", ""),
                    "location": r.get("location", ""),
                },
            }
        )
    for n in data.get("unlinkedNsgs", []):
        results.append(
            {
                "product": product,
                "check_type": "orphaned_resource",
                "status": "warning",
                "resource_type": "sg",
                "resource_id": n.get("id", ""),
                "resource_name": n.get("name", ""),
                "message": f"Security Group '{n['name']}' is not linked to any Network",
            }
        )
    return results


def _check_address_overlap(product: str, data: dict) -> list[dict]:
    """Detect overlapping address spaces between Networks in the same environment."""
    results = []
    by_env: dict[str, list[dict]] = {}
    for v in data.get("networks", []):
        if v.get("isExternal"):
            continue
        env = v.get("env", "other")
        by_env.setdefault(env, []).append(v)

    for env, vnets in by_env.items():
        networks = []
        for v in vnets:
            for addr in v.get("addressSpace", []):
                try:
                    networks.append(
                        (v["name"], ipaddress.ip_network(addr, strict=False))
                    )
                except ValueError:
                    continue

        for i, (name_a, net_a) in enumerate(networks):
            for name_b, net_b in networks[i + 1 :]:
                if name_a == name_b:
                    continue
                if net_a.overlaps(net_b):
                    results.append(
                        {
                            "product": product,
                            "check_type": "address_overlap",
                            "status": "critical",
                            "resource_type": "vnet",
                            "resource_id": f"{name_a}_{name_b}",
                            "resource_name": f"{name_a} <-> {name_b}",
                            "message": f"Address overlap in {env.upper()}: {name_a} ({net_a}) overlaps {name_b} ({net_b})",
                            "details": {
                                "env": env,
                                "vnet_a": name_a,
                                "vnet_b": name_b,
                                "network_a": str(net_a),
                                "network_b": str(net_b),
                            },
                        }
                    )
    return results


def _check_missing_critical_resources(product: str, data: dict) -> list[dict]:
    """Check that production Networks have critical resources (firewalls, Security Groups)."""
    results = []
    for v in data.get("networks", []):
        if v.get("isExternal") or v.get("env") != "prd":
            continue
        res_types = {r.get("type", "").lower() for r in v.get("resources", [])}
        has_firewall = any("firewall" in t for t in res_types)
        has_sg = len(v.get("securityGroups", [])) > 0

        if not has_firewall:
            results.append(
                {
                    "product": product,
                    "check_type": "missing_firewall",
                    "status": "critical",
                    "resource_type": "vnet",
                    "resource_id": v.get("id", ""),
                    "resource_name": v["name"],
                    "message": f"Production Network '{v['name']}' has no Azure Firewall",
                    "details": {"env": "prd", "location": v.get("location", "")},
                }
            )
        if not has_sg:
            results.append(
                {
                    "product": product,
                    "check_type": "missing_sg",
                    "status": "warning",
                    "resource_type": "vnet",
                    "resource_id": v.get("id", ""),
                    "resource_name": v["name"],
                    "message": f"Production Network '{v['name']}' has no Security Groups attached",
                    "details": {"env": "prd", "location": v.get("location", "")},
                }
            )
    return results


def _check_vnet_isolation(product: str, data: dict) -> list[dict]:
    """Flag Networks with no peerings that might be unintentionally isolated."""
    results = []
    peered_vnets = set()
    for p in data.get("peerings", []):
        peered_vnets.add(p.get("fromId"))
        peered_vnets.add(p.get("toId"))

    for v in data.get("networks", []):
        if v.get("isExternal"):
            continue
        if v.get("id") not in peered_vnets and len(v.get("resources", [])) > 0:
            results.append(
                {
                    "product": product,
                    "check_type": "isolated_vnet",
                    "status": "warning",
                    "resource_type": "vnet",
                    "resource_id": v.get("id", ""),
                    "resource_name": v["name"],
                    "message": f"Network '{v['name']}' has {len(v['resources'])} resources but no peerings — may be isolated",
                    "details": {
                        "env": v.get("env", ""),
                        "resource_count": len(v.get("resources", [])),
                    },
                }
            )
    return results


def _check_provisioning_state(product: str, data: dict) -> list[dict]:
    """Flag resources not in Succeeded provisioning state."""
    results = []
    for v in data.get("networks", []):
        for r in v.get("resources", []):
            state = r.get("provisioning", "")
            if state and state != "Succeeded":
                results.append(
                    {
                        "product": product,
                        "check_type": "provisioning_failed",
                        "status": "critical" if state == "Failed" else "warning",
                        "resource_type": r.get("type", r.get("label", "")),
                        "resource_id": r.get("id", ""),
                        "resource_name": r.get("name", ""),
                        "message": f"Resource '{r['name']}' provisioning state: {state}",
                        "details": {"state": state, "vnet": v["name"]},
                    }
                )
    return results


def compute_health_score(checks: list[dict]) -> dict:
    """Compute an overall health score from check results."""
    total = len(checks)
    if total == 0:
        return {"score": 100, "grade": "A", "status": "healthy"}

    critical = sum(1 for c in checks if c["status"] == "critical")
    warnings = sum(1 for c in checks if c["status"] == "warning")
    healthy = sum(1 for c in checks if c["status"] == "healthy")

    # Score: start at 100, -20 per critical, -5 per warning
    score = max(0, 100 - (critical * 20) - (warnings * 5))

    if score >= 90:
        grade, status = "A", "healthy"
    elif score >= 70:
        grade, status = "B", "good"
    elif score >= 50:
        grade, status = "C", "degraded"
    elif score >= 30:
        grade, status = "D", "warning"
    else:
        grade, status = "F", "critical"

    return {
        "score": score,
        "grade": grade,
        "status": status,
        "total_checks": total,
        "critical": critical,
        "warnings": warnings,
        "healthy": healthy,
    }
