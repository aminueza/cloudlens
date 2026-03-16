"""Helper utilities for graph building and resource matching."""

import re
from collections import defaultdict
from typing import Any


def safe_id(s: str) -> str:
    """Replace non-alphanumeric chars with underscore."""
    return re.sub(r"[^a-zA-Z0-9_]", "_", str(s))


def extract_network_from_subnet(subnet_ref: str) -> tuple[str | None, str | None]:
    """Extract network + subnet name from a provider-specific subnet reference.

    Handles Azure ARM IDs, AWS subnet IDs, and GCP self-links.
    """
    # Azure: /virtualNetworks/NAME/subnets/SUBNET
    m = re.search(
        r"/virtualNetworks/([^/]+)/subnets/([^/]+)", subnet_ref, re.IGNORECASE
    )
    if m:
        return m.group(1), m.group(2)
    # AWS: subnet references don't contain VPC name directly
    # GCP: projects/P/regions/R/subnetworks/NAME
    m = re.search(r"/subnetworks/([^/]+)", subnet_ref)
    if m:
        return None, m.group(1)
    return None, None


def extract_network_name(resource_id: str) -> str | None:
    """Extract network name from various provider ID formats."""
    parts = str(resource_id).split("/")
    for i, p in enumerate(parts):
        if p.lower() == "virtualnetworks" and i + 1 < len(parts):
            return parts[i + 1]
    # AWS VPC ID pattern
    if resource_id.startswith("vpc-"):
        return resource_id
    return None


def build_resource_index(
    networks: list, interfaces: list
) -> tuple[dict[tuple, set], dict[tuple, dict]]:
    """Build indexes for resource-to-network matching.

    Returns (account_region_networks, interface_network_map).
    """
    acct_nets: dict[tuple, set] = defaultdict(set)
    iface_map: dict[tuple, dict] = {}

    for n in networks:
        key = (_attr(n, "account_id"), _attr(n, "region"))
        acct_nets[key].add(_attr(n, "name"))

    for iface in interfaces:
        parent = _attr(iface, "parent_network")
        if parent:
            key = (_attr(iface, "account_id"), _attr(iface, "region"))
            iface_map[key] = {
                "network": parent,
                "subnet": _attr(iface, "subnet"),
                "ip": _attr(iface, "private_ip") or "",
            }
            acct_nets[key].add(parent)

    return acct_nets, iface_map


def find_network_for_resource(
    resource: object,
    acct_nets: dict[tuple, set],
    iface_map: dict[tuple, dict],
    networks_in_account: list,
) -> tuple[str | None, str | None, str | None]:
    """Heuristic matching to find which network a resource belongs to.

    Returns (network_name, subnet, private_ip).
    """
    acct = _attr(resource, "account_id")
    region = _attr(resource, "region")
    name = (_attr(resource, "name") or "").lower()

    key = (acct, region)

    # 1. Direct interface mapping
    if key in iface_map:
        info = iface_map[key]
        return info["network"], info.get("subnet"), info.get("ip")

    # 2. Resource has parent_network set by provider
    parent = _attr(resource, "parent_network")
    if parent:
        return parent, _attr(resource, "subnet"), _attr(resource, "private_ip")

    # 3. Single network in account+region
    if key in acct_nets and len(acct_nets[key]) == 1:
        return list(acct_nets[key])[0], None, None

    # 4. Name-based matching
    for n in networks_in_account:
        nname = (_attr(n, "name") or "").lower()
        nparts = set(nname.replace("-", "_").split("_"))
        rparts = set(name.replace("-", "_").split("_"))
        n_region = _attr(n, "region")
        if len(nparts & rparts) >= 2 and region == n_region:
            return _attr(n, "name"), None, None

    # 5. Region-based fallback
    region_nets = {
        _attr(n, "name") for n in networks_in_account if _attr(n, "region") == region
    }
    if len(region_nets) == 1:
        return list(region_nets)[0], None, None

    return None, None, None


def esc(s: str) -> str:
    """XML entity escaping for SVG."""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _attr(obj: object, field: str, default: Any = None) -> Any:
    """Get attribute from an object or dict, with fallback."""
    if isinstance(obj, dict):
        return obj.get(field, default)
    return getattr(obj, field, default)
