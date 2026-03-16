import pytest

from providers.base import NetworkPeering, NetworkResource


@pytest.fixture
def sample_networks():
    return [
        NetworkResource(
            id="azure_sub1_vnet-app-dev",
            name="vnet-app-dev",
            resource_type="virtual_network",
            provider="azure",
            account_id="sub1",
            account_name="platform-dev",
            region="eastus",
            environment="dev",
            address_space=["10.0.0.0/16"],
            subnets=[{"name": "snet-app", "prefix": "10.0.1.0/24"}],
        ),
        NetworkResource(
            id="azure_sub2_vnet-app-prd",
            name="vnet-app-prd",
            resource_type="virtual_network",
            provider="azure",
            account_id="sub2",
            account_name="platform-prd",
            region="eastus",
            environment="prd",
            address_space=["10.1.0.0/16"],
            subnets=[{"name": "snet-app", "prefix": "10.1.1.0/24"}],
        ),
        NetworkResource(
            id="aws_vpc1",
            name="vpc-data-dev",
            resource_type="virtual_network",
            provider="aws",
            account_id="123456789",
            account_name="data-dev",
            region="us-east-1",
            environment="dev",
            address_space=["172.16.0.0/16"],
        ),
    ]


@pytest.fixture
def sample_resources():
    return [
        NetworkResource(
            id="azure_sub1_fw-app-dev",
            name="fw-app-dev",
            resource_type="firewall",
            provider="azure",
            account_id="sub1",
            account_name="platform-dev",
            region="eastus",
            environment="dev",
            parent_network="vnet-app-dev",
            provisioning_state="succeeded",
        ),
        NetworkResource(
            id="azure_sub2_lb-app-prd",
            name="lb-app-prd",
            resource_type="load_balancer",
            provider="azure",
            account_id="sub2",
            account_name="platform-prd",
            region="eastus",
            environment="prd",
            parent_network="vnet-app-prd",
        ),
        NetworkResource(
            id="aws_nat1",
            name="nat-data-dev",
            resource_type="nat_gateway",
            provider="aws",
            account_id="123456789",
            account_name="data-dev",
            region="us-east-1",
            environment="dev",
            parent_network="vpc-data-dev",
        ),
    ]


@pytest.fixture
def sample_security_groups():
    return [
        NetworkResource(
            id="azure_sub1_nsg-app",
            name="nsg-app",
            resource_type="security_group",
            provider="azure",
            account_id="sub1",
            account_name="platform-dev",
            region="eastus",
            environment="dev",
            rules_count=12,
        ),
        NetworkResource(
            id="aws_sg1",
            name="sg-default",
            resource_type="security_group",
            provider="aws",
            account_id="123456789",
            account_name="data-dev",
            region="us-east-1",
            environment="dev",
            rules_count=0,
            parent_network="vpc-data-dev",
        ),
    ]


@pytest.fixture
def sample_interfaces():
    return [
        NetworkResource(
            id="azure_sub1_nic1",
            name="nic-app-1",
            resource_type="network_interface",
            provider="azure",
            account_id="sub1",
            account_name="platform-dev",
            region="eastus",
            environment="dev",
            parent_network="vnet-app-dev",
            subnet="snet-app",
            private_ip="10.0.1.4",
        ),
    ]


@pytest.fixture
def sample_peerings():
    return [
        NetworkPeering(
            id="peer_vnet-app-dev_vnet-app-prd",
            name="peer-dev-to-prd",
            provider="azure",
            source_network="azure_sub1_vnet-app-dev",
            target_network="azure_sub2_vnet-app-prd",
            state="Connected",
            source_account="sub1",
            target_account="sub2",
        ),
    ]


@pytest.fixture
def sample_structured():
    return {
        "networks": [
            {
                "id": "azure_sub1_vnet-app-dev",
                "name": "vnet-app-dev",
                "env": "dev",
                "provider": "azure",
                "account_id": "sub1",
                "region": "eastus",
                "addressSpace": ["10.0.0.0/16"],
                "subnets": [{"name": "snet-app", "prefix": "10.0.1.0/24"}],
                "resources": [
                    {
                        "id": "r1",
                        "name": "fw-app-dev",
                        "resource_type": "firewall",
                        "label": "Firewall",
                    },
                ],
                "securityGroups": [{"id": "n1", "name": "nsg-app", "rules_count": 12}],
            },
            {
                "id": "azure_sub2_vnet-app-prd",
                "name": "vnet-app-prd",
                "env": "prd",
                "provider": "azure",
                "account_id": "sub2",
                "region": "eastus",
                "addressSpace": ["10.1.0.0/16"],
                "subnets": [],
                "resources": [
                    {
                        "id": "r2",
                        "name": "lb-app-prd",
                        "resource_type": "load_balancer",
                        "label": "LB",
                    },
                ],
                "securityGroups": [],
            },
            {
                "id": "aws_vpc1",
                "name": "vpc-data-dev",
                "env": "dev",
                "provider": "aws",
                "account_id": "123456789",
                "region": "us-east-1",
                "addressSpace": ["172.16.0.0/16"],
                "subnets": [],
                "resources": [],
                "securityGroups": [
                    {"id": "sg1", "name": "sg-default", "rules_count": 0}
                ],
            },
        ],
        "peerings": [
            {
                "id": "peer1",
                "name": "peer-dev-to-prd",
                "fromId": "azure_sub1_vnet-app-dev",
                "toId": "azure_sub2_vnet-app-prd",
                "state": "Connected",
            },
        ],
        "unlinkedResources": [],
        "unlinkedSecurityGroups": [],
        "stats": {"networks": 3, "resources": 3, "peerings": 1, "externalNetworks": 0},
    }
