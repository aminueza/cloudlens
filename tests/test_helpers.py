from graph.helpers import esc, extract_network_from_subnet, safe_id


def test_safe_id():
    assert safe_id("hello-world/foo") == "hello_world_foo"


def test_extract_network_azure():
    vnet, subnet = extract_network_from_subnet(
        "/subscriptions/x/resourceGroups/rg/providers/Microsoft.Network/virtualNetworks/vnet1/subnets/snet1"
    )
    assert vnet == "vnet1"
    assert subnet == "snet1"


def test_extract_network_no_match():
    assert extract_network_from_subnet("something-random") == (None, None)


def test_esc():
    assert esc('<b>"hi"</b>') == "&lt;b&gt;&quot;hi&quot;&lt;/b&gt;"
