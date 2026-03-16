from engine.compliance import evaluate_rules


def _topo(networks=None, peerings=None, unlinked=None):
    return {
        "networks": networks or [],
        "peerings": peerings or [],
        "unlinkedResources": unlinked or [],
        "unlinkedSecurityGroups": [],
    }


def _rule(name, rule_type, config=None, severity="warning"):
    return {
        "id": 1,
        "name": name,
        "description": "",
        "severity": severity,
        "rule_type": rule_type,
        "rule_config": config or {},
        "enabled": True,
    }


class TestCompliance:
    def test_missing_firewall(self):
        topo = _topo(
            networks=[
                {
                    "id": "v1",
                    "name": "net-prd",
                    "env": "prd",
                    "resources": [],
                    "securityGroups": [],
                    "subnets": [],
                }
            ]
        )
        rules = [
            _rule(
                "fw",
                "require_resource",
                {"env": "prd", "resource_type": "firewall"},
                "critical",
            )
        ]
        assert len(evaluate_rules("test", topo, rules)) == 1

    def test_has_firewall(self):
        topo = _topo(
            networks=[
                {
                    "id": "v1",
                    "name": "net-prd",
                    "env": "prd",
                    "resources": [{"resource_type": "firewall"}],
                    "securityGroups": [],
                    "subnets": [],
                }
            ]
        )
        rules = [
            _rule("fw", "require_resource", {"env": "prd", "resource_type": "firewall"})
        ]
        assert evaluate_rules("test", topo, rules) == []

    def test_peering_disconnected(self):
        topo = _topo(peerings=[{"id": "p1", "name": "peer-1", "state": "Disconnected"}])
        rules = [_rule("peer", "peering_connected")]
        assert len(evaluate_rules("test", topo, rules)) == 1

    def test_peering_connected(self):
        topo = _topo(peerings=[{"id": "p1", "name": "peer-1", "state": "Connected"}])
        rules = [_rule("peer", "peering_connected")]
        assert evaluate_rules("test", topo, rules) == []

    def test_disabled_rule(self):
        topo = _topo(peerings=[{"id": "p1", "name": "peer-1", "state": "Disconnected"}])
        rules = [
            {
                "id": 1,
                "name": "off",
                "rule_type": "peering_connected",
                "rule_config": {},
                "enabled": False,
            }
        ]
        assert evaluate_rules("test", topo, rules) == []

    def test_address_overlap(self):
        topo = _topo(
            networks=[
                {
                    "id": "v1",
                    "name": "a",
                    "env": "dev",
                    "addressSpace": ["10.0.0.0/16"],
                    "resources": [],
                    "securityGroups": [],
                    "subnets": [],
                },
                {
                    "id": "v2",
                    "name": "b",
                    "env": "dev",
                    "addressSpace": ["10.0.1.0/24"],
                    "resources": [],
                    "securityGroups": [],
                    "subnets": [],
                },
            ]
        )
        rules = [_rule("overlap", "address_overlap")]
        assert len(evaluate_rules("test", topo, rules)) == 1
