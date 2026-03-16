from engine.health import compute_health_score, run_health_checks


def _topo(networks=None, peerings=None, unlinked=None):
    return {
        "networks": networks or [],
        "peerings": peerings or [],
        "unlinkedResources": unlinked or [],
        "unlinkedSecurityGroups": [],
        "stats": {},
    }


class TestHealthChecks:
    def test_disconnected_peering(self):
        topo = _topo(
            peerings=[
                {
                    "id": "p1",
                    "name": "peer-bad",
                    "fromId": "v1",
                    "toId": "v2",
                    "state": "Disconnected",
                }
            ]
        )
        checks = run_health_checks("test", topo)
        assert any(c["status"] == "critical" for c in checks)

    def test_empty_security_group(self):
        topo = _topo(
            networks=[
                {
                    "id": "v1",
                    "name": "net-a",
                    "env": "dev",
                    "resources": [],
                    "securityGroups": [
                        {"id": "sg1", "name": "sg-empty", "rules_count": 0}
                    ],
                    "subnets": [],
                    "addressSpace": [],
                }
            ]
        )
        checks = run_health_checks("test", topo)
        assert any("0" in c["message"] and c["status"] == "warning" for c in checks)

    def test_missing_firewall_prod(self):
        topo = _topo(
            networks=[
                {
                    "id": "v1",
                    "name": "net-prd",
                    "env": "prd",
                    "resources": [
                        {"id": "r1", "name": "lb1", "resource_type": "load_balancer"}
                    ],
                    "securityGroups": [],
                    "subnets": [],
                    "addressSpace": [],
                }
            ]
        )
        checks = run_health_checks("test", topo)
        assert any("firewall" in c["message"].lower() for c in checks)

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
                    "addressSpace": ["10.0.0.0/24"],
                    "resources": [],
                    "securityGroups": [],
                    "subnets": [],
                },
            ]
        )
        checks = run_health_checks("test", topo)
        assert any("overlap" in c["message"].lower() for c in checks)

    def test_healthy_peerings(self):
        topo = _topo(
            peerings=[
                {
                    "id": "p1",
                    "name": "ok",
                    "fromId": "v1",
                    "toId": "v2",
                    "state": "Connected",
                }
            ]
        )
        checks = run_health_checks("test", topo)
        assert any(c["status"] == "healthy" for c in checks)


class TestHealthScore:
    def test_perfect(self):
        assert compute_health_score([{"status": "healthy"}])["score"] == 100

    def test_critical_lowers(self):
        score = compute_health_score([{"status": "critical"}, {"status": "healthy"}])
        assert score["score"] <= 80

    def test_empty(self):
        assert compute_health_score([])["score"] == 100
