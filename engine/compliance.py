"""Compliance rules engine — evaluates topology against configurable rules."""

import ipaddress
import json
import logging

logger = logging.getLogger(__name__)


def evaluate_rules(product: str, structured: dict, rules: list[dict]) -> list[dict]:
    """Evaluate all enabled compliance rules against topology. Returns violations."""
    violations = []
    for rule in rules:
        if not rule.get("enabled", True):
            continue
        rule_type = rule["rule_type"]
        config = rule.get("rule_config", {})
        if isinstance(config, str):
            config = json.loads(config)

        handler = _RULE_HANDLERS.get(rule_type)
        if handler:
            try:
                violations.extend(handler(product, structured, rule, config))
            except Exception:
                logger.exception("Error evaluating rule %s", rule["name"])
    return violations


def _check_require_resource(
    product: str, data: dict, rule: dict, config: dict
) -> list[dict]:
    """Check that Networks in a given environment have a specific resource type."""
    env_filter = config.get("env")
    required_type = config.get("resource_type", "").lower()
    violations = []

    for v in data.get("networks", []):
        if v.get("isExternal"):
            continue
        if env_filter and v.get("env") != env_filter:
            continue

        if required_type == "sg":
            has_it = len(v.get("securityGroups", [])) > 0
        else:
            has_it = any(
                required_type in r.get("type", r.get("resource_type", "")).lower()
                for r in v.get("resources", [])
            )

        if not has_it:
            violations.append(
                {
                    "rule_id": rule["id"],
                    "rule_name": rule["name"],
                    "product": product,
                    "resource_type": "vnet",
                    "resource_id": v.get("id", ""),
                    "resource_name": v["name"],
                    "details": {
                        "message": f"Network '{v['name']}' ({v.get('env', '').upper()}) missing required {required_type}",
                        "env": v.get("env", ""),
                        "required_type": required_type,
                    },
                }
            )
    return violations


def _check_peering_connected(
    product: str, data: dict, rule: dict, config: dict
) -> list[dict]:
    """All peerings must be Connected."""
    violations = []
    for p in data.get("peerings", []):
        if p.get("state") != "Connected":
            violations.append(
                {
                    "rule_id": rule["id"],
                    "rule_name": rule["name"],
                    "product": product,
                    "resource_type": "peering",
                    "resource_id": p.get("id", ""),
                    "resource_name": p.get("name", ""),
                    "details": {
                        "message": f"Peering '{p.get('name')}' state: {p.get('state')}",
                        "state": p.get("state"),
                    },
                }
            )
    return violations


def _check_sg_has_rules(
    product: str, data: dict, rule: dict, config: dict
) -> list[dict]:
    """Security Groups must have at least one rule."""
    violations = []
    for v in data.get("networks", []):
        for sg in v.get("securityGroups", []):
            if sg.get("rules", 0) == 0:
                violations.append(
                    {
                        "rule_id": rule["id"],
                        "rule_name": rule["name"],
                        "product": product,
                        "resource_type": "sg",
                        "resource_id": sg.get("id", ""),
                        "resource_name": sg.get("name", ""),
                        "details": {
                            "message": f"Security Group '{sg['name']}' has 0 security rules",
                            "vnet": v["name"],
                        },
                    }
                )
    return violations


def _check_address_overlap(
    product: str, data: dict, rule: dict, config: dict
) -> list[dict]:
    """No overlapping address spaces within same environment."""
    violations = []
    by_env: dict[str, list] = {}
    for v in data.get("networks", []):
        if v.get("isExternal"):
            continue
        by_env.setdefault(v.get("env", "other"), []).append(v)

    for env, vnets in by_env.items():
        nets = []
        for v in vnets:
            for addr in v.get("addressSpace", []):
                try:
                    nets.append((v, ipaddress.ip_network(addr, strict=False)))
                except ValueError:
                    continue
        for i, (va, na) in enumerate(nets):
            for vb, nb in nets[i + 1 :]:
                if va["name"] == vb["name"]:
                    continue
                if na.overlaps(nb):
                    violations.append(
                        {
                            "rule_id": rule["id"],
                            "rule_name": rule["name"],
                            "product": product,
                            "resource_type": "vnet",
                            "resource_id": f"{va.get('id', '')}_{vb.get('id', '')}",
                            "resource_name": f"{va['name']} <-> {vb['name']}",
                            "details": {
                                "message": f"Overlap: {va['name']} ({na}) and {vb['name']} ({nb}) in {env.upper()}",
                                "env": env,
                            },
                        }
                    )
    return violations


def _check_subnet_has_sg(
    product: str, data: dict, rule: dict, config: dict
) -> list[dict]:
    """Subnets in specified environment should have Security Groups."""
    env_filter = config.get("env")
    violations = []
    for v in data.get("networks", []):
        if v.get("isExternal"):
            continue
        if env_filter and v.get("env") != env_filter:
            continue
        sg_names = {n.get("name", "") for n in v.get("securityGroups", [])}
        if not sg_names and v.get("subnets"):
            violations.append(
                {
                    "rule_id": rule["id"],
                    "rule_name": rule["name"],
                    "product": product,
                    "resource_type": "vnet",
                    "resource_id": v.get("id", ""),
                    "resource_name": v["name"],
                    "details": {
                        "message": f"Network '{v['name']}' has {len(v['subnets'])} subnets but no Security Groups",
                        "subnet_count": len(v.get("subnets", [])),
                    },
                }
            )
    return violations


def _check_no_orphan_resource(
    product: str, data: dict, rule: dict, config: dict
) -> list[dict]:
    """Flag unlinked resources of a specific type."""
    target_type = config.get("resource_type", "").lower()
    violations = []
    for r in data.get("unlinkedResources", []):
        if target_type and target_type not in r.get("type", "").lower():
            continue
        violations.append(
            {
                "rule_id": rule["id"],
                "rule_name": rule["name"],
                "product": product,
                "resource_type": r.get("type", r.get("label", "resource")),
                "resource_id": r.get("id", ""),
                "resource_name": r.get("name", ""),
                "details": {
                    "message": f"Orphaned resource: {r.get('name', '')} ({r.get('label', '')})"
                },
            }
        )
    return violations


_RULE_HANDLERS = {
    "require_resource": _check_require_resource,
    "peering_connected": _check_peering_connected,
    "sg_has_rules": _check_sg_has_rules,
    "address_overlap": _check_address_overlap,
    "subnet_has_sg": _check_subnet_has_sg,
    "no_orphan_resource": _check_no_orphan_resource,
}
