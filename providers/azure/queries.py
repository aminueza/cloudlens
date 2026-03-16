QUERIES = {
    "vnets": """
        resources
        | where type =~ 'microsoft.network/virtualnetworks'
        | project subscriptionId, resourceGroup, name, location,
                  addressSpace = properties.addressSpace.addressPrefixes,
                  subnets = array_length(properties.subnets),
                  peerings = properties.virtualNetworkPeerings
        | mv-expand peering = peerings
        | extend peeringName = tostring(peering.name),
                 peeringState = tostring(peering.properties.peeringState),
                 remoteVnet = tostring(peering.properties.remoteVirtualNetwork.id)
        | project subscriptionId, resourceGroup, vnetName=name, location,
                  addressSpace, subnetCount=subnets,
                  peeringName, peeringState, remoteVnet
    """,
    "vnets_with_subnets": """
        resources
        | where type =~ 'microsoft.network/virtualnetworks'
        | extend subnetList = properties.subnets
        | mv-expand subnet = subnetList
        | extend subnetName = tostring(subnet.name),
                 subnetPrefix = tostring(subnet.properties.addressPrefix)
        | project subscriptionId, resourceGroup, vnetName=name, location,
                  addressSpace=properties.addressSpace.addressPrefixes,
                  subnetName, subnetPrefix,
                  peerings = properties.virtualNetworkPeerings
    """,
    "resources": """
        resources
        | where type in~ (
            'microsoft.network/loadbalancers',
            'microsoft.network/applicationgateways',
            'microsoft.network/azurefirewalls',
            'microsoft.network/privateendpoints',
            'microsoft.network/natgateways',
            'microsoft.network/publicipaddresses',
            'microsoft.network/virtualnetworkgateways',
            'microsoft.network/expressroutecircuits',
            'microsoft.network/frontdoors',
            'microsoft.network/trafficmanagerprofiles',
            'microsoft.network/privatednszones',
            'microsoft.network/dnszones',
            'microsoft.network/bastionhosts')
        | project subscriptionId, resourceGroup, type, name, location,
                  provisioningState = tostring(properties.provisioningState)
    """,
    "nsgs": """
        resources
        | where type =~ 'microsoft.network/networksecuritygroups'
        | project subscriptionId, resourceGroup, name, location,
                  rules = array_length(properties.securityRules)
    """,
    "nics": """
        resources
        | where type =~ 'microsoft.network/networkinterfaces'
        | mv-expand ipconfig = properties.ipConfigurations
        | extend subnetId = tostring(ipconfig.properties.subnet.id),
                 privateIp = tostring(ipconfig.properties.privateIPAddress),
                 vmId = tostring(properties.virtualMachine.id)
        | project subscriptionId, resourceGroup, nicName=name, location,
                  subnetId, privateIp, vmId
    """,
}

VNET_COUNT_QUERY = (
    "resources "
    "| where type =~ 'microsoft.network/virtualnetworks' "
    "| summarize count()"
)

# Azure resource type → normalized type
AZURE_TYPE_MAP: dict[str, str] = {
    "microsoft.network/virtualnetworks": "virtual_network",
    "microsoft.network/azurefirewalls": "firewall",
    "microsoft.network/networksecuritygroups": "security_group",
    "microsoft.network/loadbalancers": "load_balancer",
    "microsoft.network/applicationgateways": "load_balancer",
    "microsoft.network/natgateways": "nat_gateway",
    "microsoft.network/virtualnetworkgateways": "vpn_gateway",
    "microsoft.network/privateendpoints": "private_endpoint",
    "microsoft.network/publicipaddresses": "public_ip",
    "microsoft.network/dnszones": "dns_zone",
    "microsoft.network/privatednszones": "dns_zone",
    "microsoft.network/bastionhosts": "bastion",
    "microsoft.network/expressroutecircuits": "express_route",
    "microsoft.network/frontdoors": "waf",
    "microsoft.network/trafficmanagerprofiles": "load_balancer",
    "microsoft.network/networkinterfaces": "network_interface",
}
