"""Provider registry — discovers, loads, and orchestrates cloud providers."""

import asyncio
import logging

from providers.base import NetworkPeering, NetworkResource, ProviderInterface

logger = logging.getLogger(__name__)


class AuthenticationError(Exception):
    """Raised when all providers fail authentication."""

    pass


class ProviderRegistry:
    def __init__(self, enabled: list[str]):
        self._providers: dict[str, ProviderInterface] = {}
        for name in enabled:
            try:
                self._providers[name] = self._load_provider(name)
                logger.info("Loaded provider: %s", name)
            except ImportError as e:
                logger.warning("Provider '%s' not available (missing SDK): %s", name, e)
            except Exception as e:
                logger.error("Failed to load provider '%s': %s", name, e)

    def _load_provider(self, name: str) -> ProviderInterface:
        if name == "aws":
            from providers.aws.client import AWSProvider

            return AWSProvider()
        elif name == "azure":
            from providers.azure.client import AzureProvider

            return AzureProvider()
        elif name == "gcp":
            from providers.gcp.client import GCPProvider

            return GCPProvider()
        raise ValueError(f"Unknown provider: {name}")

    def get_provider(self, name: str) -> ProviderInterface | None:
        return self._providers.get(name)

    def get_all_providers(self) -> dict[str, ProviderInterface]:
        return dict(self._providers)

    def get_auth_errors(self) -> dict[str, str]:
        errors: dict[str, str] = {}
        for name, p in self._providers.items():
            err = p.get_auth_error()
            if err:
                errors[name] = err
        return errors

    def has_auth_error(self) -> bool:
        return any(p.get_auth_error() for p in self._providers.values())

    async def fetch_all(
        self, accounts_config: dict
    ) -> tuple[
        list[NetworkResource],
        list[NetworkResource],
        list[NetworkResource],
        list[NetworkResource],
        list[NetworkResource],
        list[NetworkPeering],
    ]:
        all_networks: list[NetworkResource] = []
        all_networks_subnets: list[NetworkResource] = []
        all_resources: list[NetworkResource] = []
        all_sgs: list[NetworkResource] = []
        all_interfaces: list[NetworkResource] = []
        all_peerings: list[NetworkPeering] = []

        async def _fetch_provider(name: str, provider: ProviderInterface) -> None:
            provider_accounts = accounts_config.get(name, {})
            try:
                nets, nets_sub, res, sgs, ifaces, peers = await asyncio.gather(
                    provider.fetch_networks(provider_accounts),
                    provider.fetch_networks_with_subnets(provider_accounts),
                    provider.fetch_resources(provider_accounts),
                    provider.fetch_security_groups(provider_accounts),
                    provider.fetch_network_interfaces(provider_accounts),
                    provider.fetch_peerings(provider_accounts),
                )
                all_networks.extend(nets)
                all_networks_subnets.extend(nets_sub)
                all_resources.extend(res)
                all_sgs.extend(sgs)
                all_interfaces.extend(ifaces)
                all_peerings.extend(peers)
                provider.set_auth_error(None)
            except Exception as e:
                err_msg = f"{name}: {e}"
                provider.set_auth_error(err_msg)
                logger.error("Provider '%s' fetch failed: %s", name, e)

        await asyncio.gather(
            *[_fetch_provider(n, p) for n, p in self._providers.items()]
        )

        return (
            all_networks,
            all_networks_subnets,
            all_resources,
            all_sgs,
            all_interfaces,
            all_peerings,
        )
