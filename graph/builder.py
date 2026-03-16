"""Graph builders for network topology visualization."""

from graph.constants import (
    PROVIDER_COLORS,
    TYPE_COLORS,
    TYPE_ICONS,
    TYPE_LABELS,
)
from graph.helpers import (
    _attr,
    build_resource_index,
    find_network_for_resource,
    safe_id,
)


def build_graph(
    scope: str,
    networks: list,
    resources: list,
    security_groups: list,
    interfaces: list,
    peerings: list,
) -> dict:
    """Build a flat node/edge graph for D3.js visualization.

    Returns {"nodes": [...], "edges": [...], "stats": {...}}.
    """
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_networks: set[tuple] = set()
    node_ids: set[str] = set()

    acct_nets, iface_map = build_resource_index(networks, interfaces)

    # --- Network nodes ---
    resource_counts: dict[str, int] = {}
    for r in resources:
        net_name, _, _ = find_network_for_resource(r, acct_nets, iface_map, networks)
        if net_name:
            resource_counts[net_name] = resource_counts.get(net_name, 0) + 1

    for n in networks:
        env = _attr(n, "env") or "other"
        name = _attr(n, "name") or ""
        provider = _attr(n, "provider") or "azure"
        dedup_key = (env, name, provider)
        if dedup_key in seen_networks:
            continue
        seen_networks.add(dedup_key)

        nid = safe_id(f"net_{name}")
        node_ids.add(nid)
        count = resource_counts.get(name, 0)
        nodes.append(
            {
                "id": nid,
                "label": name,
                "type": "virtual_network",
                "icon": TYPE_ICONS.get("virtual_network", "vnet"),
                "color": PROVIDER_COLORS.get(provider, "#3b82f6"),
                "size": max(30, min(80, 30 + count * 5)),
                "env": env,
                "provider": provider,
                "account_id": _attr(n, "account_id"),
                "region": _attr(n, "region"),
            }
        )

    # --- Resource nodes ---
    for r in resources:
        rtype = _attr(r, "type") or "unknown"
        rname = _attr(r, "name") or ""
        rid = safe_id(f"res_{rname}_{_attr(r, 'id') or rname}")
        if rid in node_ids:
            continue
        node_ids.add(rid)

        nodes.append(
            {
                "id": rid,
                "label": rname,
                "type": rtype,
                "icon": TYPE_ICONS.get(rtype, "unknown"),
                "color": TYPE_COLORS.get(rtype, "#6b7280"),
                "size": 24,
                "env": _attr(r, "env") or "other",
                "provider": _attr(r, "provider") or "azure",
            }
        )

        # Edge: resource -> network
        net_name, subnet, private_ip = find_network_for_resource(
            r, acct_nets, iface_map, networks
        )
        if net_name:
            net_nid = safe_id(f"net_{net_name}")
            if net_nid in node_ids:
                edges.append(
                    {
                        "source": rid,
                        "target": net_nid,
                        "type": "contains",
                        "color": TYPE_COLORS.get(rtype, "#6b7280"),
                        "subnet": subnet,
                        "private_ip": private_ip,
                    }
                )

    # --- Security group nodes ---
    for sg in security_groups:
        sg_name = _attr(sg, "name") or ""
        sg_id = safe_id(f"sg_{sg_name}")
        if sg_id in node_ids:
            continue
        node_ids.add(sg_id)

        nodes.append(
            {
                "id": sg_id,
                "label": sg_name,
                "type": "security_group",
                "icon": TYPE_ICONS.get("security_group", "nsg"),
                "color": TYPE_COLORS.get("security_group", "#ef4444"),
                "size": 20,
                "env": _attr(sg, "env") or "other",
                "provider": _attr(sg, "provider") or "azure",
            }
        )

    # --- Peering edges ---
    for p in peerings:
        src_name = _attr(p, "source_network") or _attr(p, "local_network") or ""
        tgt_name = _attr(p, "target_network") or _attr(p, "remote_network") or ""
        state = (_attr(p, "state") or "").lower()
        src_id = safe_id(f"net_{src_name}")
        tgt_id = safe_id(f"net_{tgt_name}")

        connected = state in ("connected", "active")
        edges.append(
            {
                "source": src_id,
                "target": tgt_id,
                "type": "peering",
                "color": "#22c55e" if connected else "#ef4444",
                "state": state,
                "label": f"peering ({state})",
            }
        )

    stats = {
        "networks": len(seen_networks),
        "resources": len(resources),
        "peerings": len(peerings),
        "connections": len(edges),
    }

    return {"nodes": nodes, "edges": edges, "stats": stats}


def build_structured_graph(
    scope: str,
    networks: list,
    networks_with_subnets: list,
    resources: list,
    security_groups: list,
    interfaces: list,
    peerings: list,
) -> dict:
    """Build a structured, hierarchical graph where resources are nested under networks.

    Returns {
        "networks": [...],
        "peerings": [...],
        "unlinkedResources": [...],
        "unlinkedSecurityGroups": [...],
        "stats": {...},
    }.
    """
    acct_nets, iface_map = build_resource_index(networks, interfaces)

    # Build subnet lookup from networks_with_subnets
    subnet_lookup: dict[str, list[dict]] = {}
    for n in networks_with_subnets:
        name = _attr(n, "name") or ""
        subnets = _attr(n, "subnets") or []
        subnet_list = []
        for s in subnets:
            subnet_list.append(
                {
                    "name": _attr(s, "name") or "",
                    "addressPrefix": _attr(s, "address_prefix")
                    or _attr(s, "addressPrefix")
                    or "",
                    "securityGroup": _attr(s, "security_group")
                    or _attr(s, "securityGroup"),
                }
            )
        subnet_lookup[name] = subnet_list

    # Build network entries
    net_entries: dict[str, dict] = {}
    seen: set[tuple] = set()

    for n in networks:
        name = _attr(n, "name") or ""
        env = _attr(n, "env") or "other"
        provider = _attr(n, "provider") or "azure"
        dedup_key = (env, name, provider)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        nid = safe_id(f"net_{name}")
        net_entries[name] = {
            "id": nid,
            "name": name,
            "env": env,
            "provider": provider,
            "account_id": _attr(n, "account_id"),
            "account_name": _attr(n, "account_name") or _attr(n, "account_id"),
            "region": _attr(n, "region"),
            "addressSpace": _attr(n, "address_space") or _attr(n, "addressSpace") or [],
            "subnets": subnet_lookup.get(name, []),
            "resources": [],
            "securityGroups": [],
        }

    # Place resources under networks
    unlinked_resources: list[dict] = []
    for r in resources:
        rtype = _attr(r, "type") or "unknown"
        rname = _attr(r, "name") or ""
        net_name, subnet, private_ip = find_network_for_resource(
            r, acct_nets, iface_map, networks
        )

        entry = {
            "id": safe_id(f"res_{rname}_{_attr(r, 'id') or rname}"),
            "name": rname,
            "type": rtype,
            "label": TYPE_LABELS.get(rtype, rtype),
            "icon": TYPE_ICONS.get(rtype, "unknown"),
            "color": TYPE_COLORS.get(rtype, "#6b7280"),
            "provider": _attr(r, "provider") or "azure",
            "region": _attr(r, "region"),
            "subnet": subnet,
            "privateIp": private_ip,
            "provisioningState": _attr(r, "provisioning_state")
            or _attr(r, "provisioningState"),
        }

        if net_name and net_name in net_entries:
            net_entries[net_name]["resources"].append(entry)
        else:
            unlinked_resources.append(entry)

    # Place security groups under networks
    unlinked_sgs: list[dict] = []
    for sg in security_groups:
        sg_name = _attr(sg, "name") or ""
        sg_net = _attr(sg, "parent_network") or _attr(sg, "network") or ""
        rules = _attr(sg, "rules") or []

        entry = {
            "id": safe_id(f"sg_{sg_name}"),
            "name": sg_name,
            "type": "security_group",
            "label": TYPE_LABELS.get("security_group", "Security Group"),
            "icon": TYPE_ICONS.get("security_group", "nsg"),
            "ruleCount": len(rules) if isinstance(rules, list) else 0,
            "provider": _attr(sg, "provider") or "azure",
        }

        if sg_net and sg_net in net_entries:
            net_entries[sg_net]["securityGroups"].append(entry)
        else:
            unlinked_sgs.append(entry)

    # Peerings
    peering_entries: list[dict] = []
    external_count = 0
    for p in peerings:
        src = _attr(p, "source_network") or _attr(p, "local_network") or ""
        tgt = _attr(p, "target_network") or _attr(p, "remote_network") or ""
        state = (_attr(p, "state") or "").lower()
        is_external = tgt not in net_entries

        if is_external:
            external_count += 1

        peering_entries.append(
            {
                "source": safe_id(f"net_{src}"),
                "target": safe_id(f"net_{tgt}"),
                "sourceName": src,
                "targetName": tgt,
                "state": state,
                "isExternal": is_external,
                "provider": _attr(p, "provider") or "azure",
            }
        )

    total_resources = sum(len(ne["resources"]) for ne in net_entries.values()) + len(
        unlinked_resources
    )

    stats = {
        "networks": len(net_entries),
        "resources": total_resources,
        "peerings": len(peering_entries),
        "externalNetworks": external_count,
    }

    return {
        "networks": list(net_entries.values()),
        "peerings": peering_entries,
        "unlinkedResources": unlinked_resources,
        "unlinkedSecurityGroups": unlinked_sgs,
        "stats": stats,
    }
