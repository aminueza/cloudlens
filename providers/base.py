"""Provider abstraction — common schema and interface for all cloud providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class NetworkResource:
    id: str
    name: str
    resource_type: str  # normalized: virtual_network, firewall, security_group, etc.
    provider: str  # aws, azure, gcp
    account_id: str
    account_name: str
    region: str
    environment: str
    address_space: list[str] = field(default_factory=list)
    properties: dict = field(default_factory=dict)
    tags: dict[str, str] = field(default_factory=dict)
    provisioning_state: str = "succeeded"
    parent_network: str | None = None
    subnet: str | None = None
    private_ip: str | None = None
    subnets: list[dict] = field(default_factory=list)
    rules_count: int = 0


@dataclass
class NetworkPeering:
    id: str
    name: str
    provider: str
    source_network: str
    target_network: str
    state: str  # connected, active, disconnected, pending, etc.
    source_account: str = ""
    target_account: str = ""
    bidirectional: bool = True


class ProviderInterface(ABC):
    """Every cloud provider implements this interface."""

    @abstractmethod
    async def fetch_networks(self) -> list[NetworkResource]: ...

    @abstractmethod
    async def fetch_networks_with_subnets(self) -> list[NetworkResource]: ...

    @abstractmethod
    async def fetch_resources(self) -> list[NetworkResource]: ...

    @abstractmethod
    async def fetch_security_groups(self) -> list[NetworkResource]: ...

    @abstractmethod
    async def fetch_network_interfaces(self) -> list[NetworkResource]: ...

    @abstractmethod
    async def fetch_peerings(self) -> list[NetworkPeering]: ...

    @abstractmethod
    def get_auth_error(self) -> str | None: ...

    @abstractmethod
    def set_auth_error(self, error: str | None) -> None: ...

    @abstractmethod
    def get_provider_name(self) -> str: ...

    def get_discovered_accounts(self) -> dict[str, str]:
        """Return mapping of account_id -> display_name. Override per provider."""
        return {}
