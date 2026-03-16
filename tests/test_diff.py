from engine.diff import compute_diff, summarize_changes


def _topo(networks=None, peerings=None):
    return {
        "networks": networks or [],
        "peerings": peerings or [],
        "unlinkedResources": [],
        "unlinkedSecurityGroups": [],
        "stats": {},
    }


class TestDiff:
    def test_no_changes(self):
        old = _topo(
            networks=[
                {
                    "id": "v1",
                    "name": "net-a",
                    "env": "dev",
                    "subnets": [],
                    "resources": [],
                    "securityGroups": [],
                    "addressSpace": ["10.0.0.0/16"],
                }
            ]
        )
        assert compute_diff("test", old, old) == []

    def test_network_added(self):
        old = _topo()
        new = _topo(
            networks=[
                {
                    "id": "v1",
                    "name": "net-new",
                    "env": "prd",
                    "subnets": [],
                    "resources": [],
                    "securityGroups": [],
                    "addressSpace": [],
                }
            ]
        )
        changes = compute_diff("test", old, new)
        assert len(changes) == 1
        assert changes[0]["change_type"] == "added"

    def test_network_removed(self):
        old = _topo(
            networks=[
                {
                    "id": "v1",
                    "name": "net-old",
                    "env": "dev",
                    "subnets": [],
                    "resources": [],
                    "securityGroups": [],
                    "addressSpace": [],
                }
            ]
        )
        changes = compute_diff("test", old, _topo())
        assert len(changes) == 1
        assert changes[0]["change_type"] == "removed"
        assert changes[0]["severity"] == "critical"

    def test_peering_state_change(self):
        old = _topo(
            peerings=[
                {
                    "id": "p1",
                    "name": "peer-1",
                    "fromId": "v1",
                    "toId": "v2",
                    "state": "Connected",
                }
            ]
        )
        new = _topo(
            peerings=[
                {
                    "id": "p1",
                    "name": "peer-1",
                    "fromId": "v1",
                    "toId": "v2",
                    "state": "Disconnected",
                }
            ]
        )
        changes = compute_diff("test", old, new)
        assert len(changes) == 1
        assert changes[0]["severity"] == "critical"

    def test_summarize_empty(self):
        assert summarize_changes([]) == "No changes detected."
