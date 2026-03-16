"""GCP provider — stub implementation. Returns empty results when GCP SDK is not installed."""

import logging

from providers.base import NetworkPeering, NetworkResource, ProviderInterface

logger = logging.getLogger(__name__)


class GCPProvider(ProviderInterface):
    def __init__(self) -> None:
        self._auth_error: str | None = None
        try:
            import google.cloud.compute_v1  # noqa: F401

            logger.info("GCP Compute SDK available")
        except ImportError:
            self._auth_error = "GCP SDK not installed. Run: pip install cloudlens[gcp]"
            logger.info("GCP provider loaded in stub mode (SDK not installed)")

    async def fetch_networks(self) -> list[NetworkResource]:
        return []

    async def fetch_networks_with_subnets(self) -> list[NetworkResource]:
        return []

    async def fetch_resources(self) -> list[NetworkResource]:
        return []

    async def fetch_security_groups(self) -> list[NetworkResource]:
        return []

    async def fetch_network_interfaces(self) -> list[NetworkResource]:
        return []

    async def fetch_peerings(self) -> list[NetworkPeering]:
        return []

    def get_auth_error(self) -> str | None:
        return self._auth_error

    def set_auth_error(self, error: str | None) -> None:
        self._auth_error = error

    def get_provider_name(self) -> str:
        return "gcp"
