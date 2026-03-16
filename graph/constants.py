"""Cloud-agnostic constants for network resource types."""

# Maps normalized resource types to display labels
TYPE_LABELS: dict[str, str] = {
    "virtual_network": "Virtual Network",
    "firewall": "Firewall",
    "security_group": "Security Group",
    "load_balancer": "Load Balancer",
    "nat_gateway": "NAT Gateway",
    "vpn_gateway": "VPN Gateway",
    "private_endpoint": "Private Endpoint",
    "public_ip": "Public IP",
    "dns_zone": "DNS Zone",
    "bastion": "Bastion",
    "express_route": "Dedicated Connection",
    "waf": "WAF",
    "network_interface": "Network Interface",
}

# Maps normalized types to SVG icon keys
TYPE_ICONS: dict[str, str] = {
    "virtual_network": "vnet",
    "firewall": "firewall",
    "security_group": "nsg",
    "load_balancer": "lb",
    "nat_gateway": "nat",
    "vpn_gateway": "vpngw",
    "private_endpoint": "pe",
    "public_ip": "pip",
    "dns_zone": "dns",
    "bastion": "bastion",
    "express_route": "er",
    "waf": "waf",
    "network_interface": "nic",
}

# Edge colors by resource type
TYPE_COLORS: dict[str, str] = {
    "virtual_network": "#3b82f6",
    "firewall": "#ef4444",
    "security_group": "#ef4444",
    "load_balancer": "#06b6d4",
    "nat_gateway": "#f59e0b",
    "vpn_gateway": "#f97316",
    "private_endpoint": "#a855f7",
    "public_ip": "#14b8a6",
    "dns_zone": "#8b5cf6",
    "bastion": "#64748b",
    "express_route": "#eab308",
    "waf": "#ec4899",
    "network_interface": "#6366f1",
}

# Cloud provider brand colors
PROVIDER_COLORS: dict[str, str] = {
    "aws": "#FF9900",
    "azure": "#0078D4",
    "gcp": "#4285F4",
}

# Environment colors
ENV_COLORS: dict[str, str] = {
    "dev": "#3b82f6",
    "stg": "#f59e0b",
    "prd": "#22c55e",
    "global": "#a855f7",
    "other": "#64748b",
}

ENV_BORDER: dict[str, str] = {
    "dev": "#2563eb",
    "stg": "#d97706",
    "prd": "#16a34a",
    "global": "#7c3aed",
    "other": "#475569",
}

# Resource types considered "key" (shown individually, not grouped)
KEY_RESOURCE_TYPES: set[str] = {
    "firewall",
    "load_balancer",
    "vpn_gateway",
    "bastion",
    "express_route",
    "nat_gateway",
    "waf",
    "dns_zone",
}
