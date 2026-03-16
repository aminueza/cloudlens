from engine.blast_radius import analyze_blast_radius, get_dependency_graph


def _topo():
    return {
        "networks": [
            {
                "id": "v1",
                "name": "hub",
                "env": "prd",
                "provider": "azure",
                "resources": [
                    {
                        "id": "r1",
                        "name": "fw-hub",
                        "resource_type": "firewall",
                        "label": "Firewall",
                    },
                    {
                        "id": "r2",
                        "name": "lb-hub",
                        "resource_type": "load_balancer",
                        "label": "LB",
                    },
                ],
                "securityGroups": [{"id": "n1", "name": "nsg-hub", "rules_count": 10}],
                "subnets": [],
            },
            {
                "id": "v2",
                "name": "spoke1",
                "env": "prd",
                "provider": "azure",
                "resources": [
                    {
                        "id": "r3",
                        "name": "pe-spoke1",
                        "resource_type": "private_endpoint",
                        "label": "PE",
                    }
                ],
                "securityGroups": [],
                "subnets": [],
            },
            {
                "id": "v3",
                "name": "spoke2",
                "env": "dev",
                "provider": "aws",
                "resources": [],
                "securityGroups": [],
                "subnets": [],
            },
        ],
        "peerings": [
            {
                "id": "p1",
                "name": "hub-spoke1",
                "fromId": "v1",
                "toId": "v2",
                "state": "Connected",
            },
            {
                "id": "p2",
                "name": "hub-spoke2",
                "fromId": "v1",
                "toId": "v3",
                "state": "Connected",
            },
        ],
        "unlinkedResources": [],
        "unlinkedSecurityGroups": [],
    }


class TestBlastRadius:
    def test_hub_blast(self):
        r = analyze_blast_radius("v1", _topo())
        assert r["resource_type"] == "vnet"
        assert len(r["directly_affected"]) >= 2
        assert len(r["indirectly_affected"]) >= 2

    def test_spoke_blast(self):
        r = analyze_blast_radius("v2", _topo())
        assert r["resource_name"] == "spoke1"

    def test_firewall_blast(self):
        r = analyze_blast_radius("r1", _topo())
        assert r["resource_type"] == "Firewall"
        assert r["total_impact"] > 0

    def test_unknown(self):
        r = analyze_blast_radius("nonexistent", _topo())
        assert r["total_impact"] == 0


class TestDependencyGraph:
    def test_structure(self):
        dep = get_dependency_graph(_topo())
        assert dep["total_nodes"] >= 3
        assert dep["total_edges"] >= 2
        assert isinstance(dep["critical_nodes"], list)
