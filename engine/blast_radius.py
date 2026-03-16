"""Blast radius analysis — determine impact of a resource going down."""

import logging

logger = logging.getLogger(__name__)


def analyze_blast_radius(resource_id: str, structured: dict) -> dict:
    """Analyze the blast radius if a specific resource goes down.

    Returns affected resources, peerings, and downstream Networks.
    """
    # Build lookup structures
    vnet_by_id = {v["id"]: v for v in structured.get("networks", [])}
    peering_graph: dict[str, list[dict]] = {}
    for p in structured.get("peerings", []):
        peering_graph.setdefault(p["fromId"], []).append(p)
        peering_graph.setdefault(p["toId"], []).append(p)

    result: dict[str, object] = {
        "resource_id": resource_id,
        "resource_name": "",
        "resource_type": "",
        "directly_affected": [],
        "indirectly_affected": [],
        "affected_peerings": [],
        "total_impact": 0,
        "severity": "low",
    }
    direct: list[dict] = []
    indirect: list[dict] = []
    peerings_hit: list[dict] = []
    res_name = ""
    res_type = ""

    # Case 1: Resource is a Network
    if resource_id in vnet_by_id:
        vnet = vnet_by_id[resource_id]
        res_name = vnet["name"]
        res_type = "vnet"

        for r in vnet.get("resources", []):
            direct.append(
                {
                    "id": r.get("id", ""),
                    "name": r.get("name", ""),
                    "type": r.get("label", r.get("type", "")),
                }
            )
        for n in vnet.get("securityGroups", []):
            direct.append(
                {
                    "id": n.get("id", ""),
                    "name": n.get("name", ""),
                    "type": "Security Group",
                }
            )

        _trace_peering_impact(
            resource_id,
            vnet_by_id,
            peering_graph,
            indirect,
            peerings_hit,
            depth=0,
            visited=set(),
        )

    else:
        # Case 2: Resource is a specific resource type (firewall, LB, etc.)
        for v in structured.get("networks", []):
            for r in v.get("resources", []):
                if r.get("id") == resource_id:
                    res_name = r.get("name", "")
                    res_type = r.get("label", r.get("type", ""))
                    if "firewall" in r.get("type", "").lower():
                        direct.append(
                            {
                                "id": v["id"],
                                "name": v["name"],
                                "type": "Network (all traffic)",
                            }
                        )
                        for other_r in v.get("resources", []):
                            if other_r.get("id") != resource_id:
                                direct.append(
                                    {
                                        "id": other_r.get("id", ""),
                                        "name": other_r.get("name", ""),
                                        "type": other_r.get("label", ""),
                                    }
                                )
                        _trace_peering_impact(
                            v["id"],
                            vnet_by_id,
                            peering_graph,
                            indirect,
                            peerings_hit,
                            0,
                            set(),
                        )
                    elif "loadbalancer" in r.get("type", "").lower():
                        direct.append(
                            {
                                "id": v["id"],
                                "name": v["name"],
                                "type": "Network (load-balanced services)",
                            }
                        )
                    elif "gateway" in r.get("type", "").lower():
                        direct.append(
                            {
                                "id": v["id"],
                                "name": v["name"],
                                "type": "Network (external connectivity)",
                            }
                        )
                        _trace_peering_impact(
                            v["id"],
                            vnet_by_id,
                            peering_graph,
                            indirect,
                            peerings_hit,
                            0,
                            set(),
                        )
                    else:
                        direct.append(
                            {"id": v["id"], "name": v["name"], "type": "Parent Network"}
                        )
                    break

    total_impact = len(direct) + len(indirect)
    if total_impact > 20:
        severity = "critical"
    elif total_impact > 10:
        severity = "high"
    elif total_impact > 3:
        severity = "medium"
    else:
        severity = "low"

    result["resource_name"] = res_name
    result["resource_type"] = res_type
    result["directly_affected"] = direct
    result["indirectly_affected"] = indirect
    result["affected_peerings"] = peerings_hit
    result["total_impact"] = total_impact
    result["severity"] = severity
    return result


def _trace_peering_impact(
    vnet_id: str,
    vnet_by_id: dict,
    peering_graph: dict,
    indirect: list[dict],
    peerings_hit: list[dict],
    depth: int,
    visited: set,
) -> None:
    """Recursively trace peering connections to find indirect impact."""
    if depth > 3 or vnet_id in visited:
        return
    visited.add(vnet_id)

    for peering in peering_graph.get(vnet_id, []):
        remote_id = (
            peering["toId"] if peering["fromId"] == vnet_id else peering["fromId"]
        )
        if remote_id in visited:
            continue

        peerings_hit.append(
            {
                "id": peering.get("id", ""),
                "name": peering.get("name", ""),
                "state": peering.get("state", ""),
                "remote_vnet": remote_id,
            }
        )

        if remote_id in vnet_by_id:
            remote_vnet = vnet_by_id[remote_id]
            indirect.append(
                {
                    "id": remote_id,
                    "name": remote_vnet["name"],
                    "type": "Peered Network",
                    "depth": depth + 1,
                    "resources_count": len(remote_vnet.get("resources", [])),
                }
            )
            _trace_peering_impact(
                remote_id,
                vnet_by_id,
                peering_graph,
                indirect,
                peerings_hit,
                depth + 1,
                visited,
            )


def get_dependency_graph(structured: dict) -> dict:
    """Build a full dependency graph showing how resources interconnect."""
    nodes = []
    edges = []

    for v in structured.get("networks", []):
        res_count = len(v.get("resources", [])) + len(v.get("securityGroups", []))
        nodes.append(
            {
                "id": v["id"],
                "name": v["name"],
                "type": "vnet",
                "env": v.get("env", ""),
                "weight": res_count,
                "is_hub": res_count > 5,  # Hub Networks typically have more resources
            }
        )

        for r in v.get("resources", []):
            nodes.append(
                {
                    "id": r.get("id", ""),
                    "name": r.get("name", ""),
                    "type": r.get("type", r.get("label", "")),
                    "parent": v["id"],
                    "weight": 1,
                    "is_critical": "firewall" in r.get("type", "").lower()
                    or "gateway" in r.get("type", "").lower(),
                }
            )
            edges.append(
                {
                    "from": r.get("id", ""),
                    "to": v["id"],
                    "type": "contains",
                }
            )

    for p in structured.get("peerings", []):
        edges.append(
            {
                "from": p["fromId"],
                "to": p["toId"],
                "type": "peering",
                "state": p.get("state", ""),
            }
        )

    # Identify critical paths (nodes that if removed, would disconnect the graph)
    critical_nodes = _find_critical_nodes(nodes, edges)

    return {
        "nodes": nodes,
        "edges": edges,
        "critical_nodes": critical_nodes,
        "total_nodes": len(nodes),
        "total_edges": len(edges),
    }


def _find_critical_nodes(nodes: list[dict], edges: list[dict]) -> list[str]:
    """Find articulation points (nodes whose removal disconnects the graph)."""
    # Build adjacency list for Network peering graph only
    adj: dict[str, set[str]] = {}
    vnet_ids = {n["id"] for n in nodes if n["type"] == "vnet"}

    for e in edges:
        if e["type"] == "peering" and e["from"] in vnet_ids and e["to"] in vnet_ids:
            adj.setdefault(e["from"], set()).add(e["to"])
            adj.setdefault(e["to"], set()).add(e["from"])

    if len(adj) < 2:
        return []

    # Tarjan's algorithm for articulation points
    visited: set[str] = set()
    disc: dict[str, int] = {}
    low: dict[str, int] = {}
    parent: dict[str, str | None] = {}
    ap: set[str] = set()
    timer = [0]

    def dfs(u: str) -> None:
        visited.add(u)
        disc[u] = low[u] = timer[0]
        timer[0] += 1
        children = 0

        for v in adj.get(u, set()):
            if v not in visited:
                children += 1
                parent[v] = u
                dfs(v)
                low[u] = min(low[u], low[v])
                if parent.get(u) is None and children > 1:
                    ap.add(u)
                if parent.get(u) is not None and low[v] >= disc[u]:
                    ap.add(u)
            elif v != parent.get(u):
                low[u] = min(low[u], disc[v])

    for node_id in adj:
        if node_id not in visited:
            parent[node_id] = None
            dfs(node_id)

    return list(ap)
