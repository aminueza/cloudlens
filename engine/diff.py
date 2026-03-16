"""Compute structured diffs between network topology snapshots."""


def compute_diff(
    scope: str,
    old_structured: dict,
    new_structured: dict,
    snapshot_id: int | None = None,
) -> list[dict]:
    """Compute changes between two structured graph snapshots.

    Indexes networks/peerings/resources by ID, performs three-way diff
    (added, removed, modified) for each category.
    """
    changes: list[dict] = []

    old_networks = _index_by_id(old_structured.get("networks", []))
    new_networks = _index_by_id(new_structured.get("networks", []))

    old_peerings = _index_peerings(old_structured.get("peerings", []))
    new_peerings = _index_peerings(new_structured.get("peerings", []))

    old_resources = _index_all_resources(old_structured.get("networks", []))
    new_resources = _index_all_resources(new_structured.get("networks", []))

    # --- Network diff ---
    for nid in new_networks.keys() - old_networks.keys():
        n = new_networks[nid]
        changes.append(
            _change(
                scope=scope,
                snapshot_id=snapshot_id,
                change_type="added",
                resource_type="virtual_network",
                resource_name=n.get("name", nid),
                severity="info",
                detail=f"Network {n.get('name', nid)} added "
                f"(provider={n.get('provider')}, region={n.get('region')})",
                provider=n.get("provider"),
            )
        )

    for nid in old_networks.keys() - new_networks.keys():
        n = old_networks[nid]
        changes.append(
            _change(
                scope=scope,
                snapshot_id=snapshot_id,
                change_type="removed",
                resource_type="virtual_network",
                resource_name=n.get("name", nid),
                severity=severity_for_change("removed", "virtual_network"),
                detail=f"Network {n.get('name', nid)} removed",
                provider=n.get("provider"),
            )
        )

    for nid in old_networks.keys() & new_networks.keys():
        old_n = old_networks[nid]
        new_n = new_networks[nid]
        diffs = _compare_network(old_n, new_n)
        if diffs:
            changes.append(
                _change(
                    scope=scope,
                    snapshot_id=snapshot_id,
                    change_type="modified",
                    resource_type="virtual_network",
                    resource_name=new_n.get("name", nid),
                    severity="info",
                    detail="; ".join(diffs),
                    provider=new_n.get("provider"),
                )
            )

    # --- Peering diff ---
    for pid in new_peerings.keys() - old_peerings.keys():
        p = new_peerings[pid]
        changes.append(
            _change(
                scope=scope,
                snapshot_id=snapshot_id,
                change_type="added",
                resource_type="peering",
                resource_name=pid,
                severity="info",
                detail=f"Peering {p.get('sourceName', '')} <-> {p.get('targetName', '')} added",
                provider=p.get("provider"),
            )
        )

    for pid in old_peerings.keys() - new_peerings.keys():
        p = old_peerings[pid]
        changes.append(
            _change(
                scope=scope,
                snapshot_id=snapshot_id,
                change_type="removed",
                resource_type="peering",
                resource_name=pid,
                severity="warning",
                detail=f"Peering {p.get('sourceName', '')} <-> {p.get('targetName', '')} removed",
                provider=p.get("provider"),
            )
        )

    for pid in old_peerings.keys() & new_peerings.keys():
        old_p = old_peerings[pid]
        new_p = new_peerings[pid]
        old_state = old_p.get("state", "")
        new_state = new_p.get("state", "")
        if old_state != new_state:
            is_disconnect = new_state not in ("connected", "active")
            changes.append(
                _change(
                    scope=scope,
                    snapshot_id=snapshot_id,
                    change_type="modified",
                    resource_type="peering",
                    resource_name=pid,
                    severity="critical" if is_disconnect else "info",
                    detail=f"Peering state changed: {old_state} -> {new_state}",
                    provider=new_p.get("provider"),
                )
            )

    # --- Resource diff ---
    for rid in new_resources.keys() - old_resources.keys():
        r = new_resources[rid]
        changes.append(
            _change(
                scope=scope,
                snapshot_id=snapshot_id,
                change_type="added",
                resource_type=r.get("type", "unknown"),
                resource_name=r.get("name", rid),
                severity="info",
                detail=f"Resource {r.get('name', rid)} ({r.get('type', 'unknown')}) added",
                provider=r.get("provider"),
            )
        )

    for rid in old_resources.keys() - new_resources.keys():
        r = old_resources[rid]
        rtype = r.get("type", "unknown")
        changes.append(
            _change(
                scope=scope,
                snapshot_id=snapshot_id,
                change_type="removed",
                resource_type=rtype,
                resource_name=r.get("name", rid),
                severity=severity_for_change("removed", rtype),
                detail=f"Resource {r.get('name', rid)} ({rtype}) removed",
                provider=r.get("provider"),
            )
        )

    for rid in old_resources.keys() & new_resources.keys():
        old_r = old_resources[rid]
        new_r = new_resources[rid]
        diffs = _compare_resource(old_r, new_r)
        if diffs:
            changes.append(
                _change(
                    scope=scope,
                    snapshot_id=snapshot_id,
                    change_type="modified",
                    resource_type=new_r.get("type", "unknown"),
                    resource_name=new_r.get("name", rid),
                    severity="info",
                    detail="; ".join(diffs),
                    provider=new_r.get("provider"),
                )
            )

    return changes


def severity_for_change(change_type: str, resource_type: str) -> str:
    """Determine severity based on change type and resource type."""
    if change_type == "removed":
        if resource_type in ("virtual_network", "firewall", "peering"):
            return "critical"
        return "warning"
    if change_type == "added":
        return "info"
    return "info"


def summarize_changes(changes: list[dict]) -> str:
    """Generate a human-readable summary of changes."""
    if not changes:
        return "No changes detected."

    added = [c for c in changes if c.get("change_type") == "added"]
    removed = [c for c in changes if c.get("change_type") == "removed"]
    modified = [c for c in changes if c.get("change_type") == "modified"]
    critical = [c for c in changes if c.get("severity") == "critical"]

    parts: list[str] = []
    parts.append(f"{len(changes)} change(s) detected:")
    if added:
        parts.append(f"  + {len(added)} added")
    if removed:
        parts.append(f"  - {len(removed)} removed")
    if modified:
        parts.append(f"  ~ {len(modified)} modified")
    if critical:
        parts.append(f"  ! {len(critical)} critical")

    for c in critical:
        parts.append(f"  [CRITICAL] {c.get('detail', '')}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _change(
    scope: str,
    snapshot_id: int | None,
    change_type: str,
    resource_type: str,
    resource_name: str,
    severity: str,
    detail: str,
    provider: str | None = None,
) -> dict:
    return {
        "scope": scope,
        "snapshot_id": snapshot_id,
        "change_type": change_type,
        "resource_type": resource_type,
        "resource_name": resource_name,
        "severity": severity,
        "detail": detail,
        "provider": provider,
    }


def _index_by_id(items: list[dict]) -> dict[str, dict]:
    """Index a list of dicts by their 'id' field."""
    return {item["id"]: item for item in items if "id" in item}


def _index_peerings(peerings: list[dict]) -> dict[str, dict]:
    """Index peerings by a composite key of source+target."""
    result: dict[str, dict] = {}
    for p in peerings:
        key = f"{p.get('source', '')}::{p.get('target', '')}"
        result[key] = p
    return result


def _index_all_resources(networks: list[dict]) -> dict[str, dict]:
    """Collect all resources from all networks into a flat index."""
    result: dict[str, dict] = {}
    for net in networks:
        for r in net.get("resources", []):
            if "id" in r:
                result[r["id"]] = r
    return result


def _compare_network(old: dict, new: dict) -> list[str]:
    """Compare two network dicts and return list of difference descriptions."""
    diffs: list[str] = []
    if old.get("addressSpace") != new.get("addressSpace"):
        diffs.append(
            f"Address space changed: {old.get('addressSpace')} -> {new.get('addressSpace')}"
        )
    old_subs = {s.get("name") for s in old.get("subnets", [])}
    new_subs = {s.get("name") for s in new.get("subnets", [])}
    added = new_subs - old_subs
    removed = old_subs - new_subs
    if added:
        diffs.append(f"Subnets added: {', '.join(sorted(added))}")
    if removed:
        diffs.append(f"Subnets removed: {', '.join(sorted(removed))}")
    old_rc = len(old.get("resources", []))
    new_rc = len(new.get("resources", []))
    if old_rc != new_rc:
        diffs.append(f"Resource count changed: {old_rc} -> {new_rc}")
    return diffs


def _compare_resource(old: dict, new: dict) -> list[str]:
    """Compare two resource dicts and return list of difference descriptions."""
    diffs: list[str] = []
    for field in ("provisioningState", "subnet", "privateIp"):
        old_val = old.get(field)
        new_val = new.get(field)
        if old_val != new_val:
            diffs.append(f"{field}: {old_val} -> {new_val}")
    return diffs
