"""Azure provider — queries Resource Graph and normalizes to common schema."""

import asyncio
import logging
import re
import time
from typing import Any

from prometheus_client import Histogram

from config.settings import get_env
from providers.azure.queries import AZURE_TYPE_MAP, QUERIES
from providers.base import NetworkPeering, NetworkResource, ProviderInterface

logger = logging.getLogger(__name__)

azure_query_duration = Histogram(
    "azure_query_duration_seconds",
    "Time spent executing Azure Resource Graph queries",
    ["query_key"],
)

_MAX_CONCURRENT = 10
_query_sem = asyncio.Semaphore(_MAX_CONCURRENT)


class AzureProvider(ProviderInterface):
    def __init__(self) -> None:
        self._client: Any = None
        self._credential: Any = None
        self._auth_error: str | None = None
        self._sub_id_to_name: dict[str, str] = {}
        self._ready = False
        self._ready_lock = asyncio.Lock()

    def _init_client(self) -> None:
        if self._client is not None:
            return
        try:
            from azure.core.pipeline.policies import RetryPolicy
            from azure.identity import DefaultAzureCredential
            from azure.mgmt.resourcegraph import ResourceGraphClient

            self._credential = DefaultAzureCredential()
            self._client = ResourceGraphClient(
                self._credential,
                retry_policy=RetryPolicy(retry_total=3, retry_backoff_factor=0.5),
                connection_verify=True,
            )
        except Exception as e:
            self._auth_error = f"Azure SDK init failed: {e}"
            logger.error("Azure init failed: %s", e)

    def _discover_subscriptions(self) -> list[str]:
        """Auto-discover all Azure subscriptions the credential has access to."""
        if not self._credential:
            return []
        try:
            from azure.mgmt.subscription import SubscriptionClient

            sub_client = SubscriptionClient(self._credential)
            sub_ids: list[str] = []
            for sub in sub_client.subscriptions.list():
                state = str(sub.state) if sub.state else ""
                if "Enabled" in state or "enabled" in state:
                    sub_id = sub.subscription_id or ""
                    display_name = sub.display_name or sub_id
                    sub_ids.append(sub_id)
                    self._sub_id_to_name[sub_id] = display_name
            logger.info(
                "Discovered %d Azure subscriptions: %s",
                len(sub_ids),
                ", ".join(self._sub_id_to_name.values()),
            )
            return sub_ids
        except Exception as e:
            logger.error("Failed to list Azure subscriptions: %s", e)
            self._auth_error = f"Azure subscription discovery failed: {e}"
            return []

    async def _ensure_ready(self) -> list[str]:
        """Init client + discover subscriptions once; all fetch methods await this."""
        async with self._ready_lock:
            if self._ready:
                return self._get_sub_ids()
            self._init_client()
            await asyncio.to_thread(self._discover_subscriptions)
            self._ready = True
        return self._get_sub_ids()

    def _query(self, query: str, sub_ids: list[str]) -> list[dict]:
        from azure.mgmt.resourcegraph.models import QueryRequest

        if not self._client:
            return []
        request = QueryRequest(
            subscriptions=sub_ids,
            query=query,
            options={"resultFormat": "objectArray", "$top": 1000},  # type: ignore[arg-type]
        )
        response = self._client.resources(request)
        results: list[dict] = list(response.data)  # type: ignore[arg-type]
        while response.skip_token:
            if request.options is not None:
                request.options["$skipToken"] = response.skip_token  # type: ignore[index]
            response = self._client.resources(request)
            results.extend(response.data)  # type: ignore[arg-type]
        return results

    async def _run_query(self, key: str, query: str, sub_ids: list[str]) -> list[dict]:
        async with _query_sem:
            try:
                start = time.monotonic()
                result = await asyncio.to_thread(self._query, query, sub_ids)
                azure_query_duration.labels(query_key=key).observe(
                    time.monotonic() - start
                )
                self._auth_error = None
                return result
            except Exception as e:
                if self._is_auth_error(e):
                    self._auth_error = self._format_auth_error(e)
                    logger.error("Azure auth failed: %s", self._auth_error)
                else:
                    logger.warning("Azure query '%s' failed: %s", key, e)
                return []

    def _is_auth_error(self, exc: Exception) -> bool:
        msg = str(exc).lower()
        return any(
            s in msg
            for s in [
                "defaultazurecredential failed",
                "aadsts70043",
                "refresh token has expired",
                "authentication unavailable",
            ]
        )

    def _format_auth_error(self, exc: Exception) -> str:
        msg = str(exc)
        if "AADSTS70043" in msg or "refresh token" in msg:
            return "Azure CLI token expired. Run: az login"
        if "DefaultAzureCredential failed" in msg:
            return "Azure authentication failed. Run: az login"
        return f"Azure auth error: {msg[:200]}"

    def _get_sub_ids(self) -> list[str]:
        """Return all discovered subscription IDs."""
        return list(self._sub_id_to_name.keys())

    def _normalize_network(self, raw: dict) -> NetworkResource:
        sub_id = raw["subscriptionId"]
        name = raw.get("vnetName", raw.get("name", ""))
        acct_name = self._sub_id_to_name.get(sub_id, "")
        return NetworkResource(
            id=f"azure_{sub_id}_{name}",
            name=name,
            resource_type="virtual_network",
            provider="azure",
            account_id=sub_id,
            account_name=acct_name,
            region=raw.get("location", ""),
            environment=get_env(acct_name),
            address_space=raw.get("addressSpace") or [],
            properties=raw,
            provisioning_state="succeeded",
        )

    def _normalize_resource(self, raw: dict) -> NetworkResource:
        sub_id = raw["subscriptionId"]
        rtype = raw.get("type", "").lower()
        acct_name = self._sub_id_to_name.get(sub_id, "")
        return NetworkResource(
            id=f"azure_{sub_id}_{raw['name']}",
            name=raw["name"],
            resource_type=AZURE_TYPE_MAP.get(rtype, rtype.split("/")[-1]),
            provider="azure",
            account_id=sub_id,
            account_name=acct_name,
            region=raw.get("location", ""),
            environment=get_env(acct_name),
            properties=raw,
            provisioning_state=raw.get("provisioningState", ""),
        )

    async def fetch_networks(self) -> list[NetworkResource]:
        sub_ids = await self._ensure_ready()
        if not sub_ids:
            return []
        raw = await self._run_query("vnets", QUERIES["vnets"], sub_ids)
        return [self._normalize_network(r) for r in raw]

    async def fetch_networks_with_subnets(self) -> list[NetworkResource]:
        sub_ids = await self._ensure_ready()
        if not sub_ids:
            return []
        raw = await self._run_query(
            "vnets_with_subnets", QUERIES["vnets_with_subnets"], sub_ids
        )
        return [self._normalize_network(r) for r in raw]

    async def fetch_resources(self) -> list[NetworkResource]:
        sub_ids = await self._ensure_ready()
        if not sub_ids:
            return []
        raw = await self._run_query("resources", QUERIES["resources"], sub_ids)
        return [self._normalize_resource(r) for r in raw]

    async def fetch_security_groups(self) -> list[NetworkResource]:
        sub_ids = await self._ensure_ready()
        if not sub_ids:
            return []
        raw = await self._run_query("nsgs", QUERIES["nsgs"], sub_ids)
        result = []
        for r in raw:
            sub_id = r["subscriptionId"]
            acct_name = self._sub_id_to_name.get(sub_id, "")
            result.append(
                NetworkResource(
                    id=f"azure_{sub_id}_{r['name']}",
                    name=r["name"],
                    resource_type="security_group",
                    provider="azure",
                    account_id=sub_id,
                    account_name=acct_name,
                    region=r.get("location", ""),
                    environment=get_env(acct_name),
                    rules_count=r.get("rules", 0) or 0,
                    properties=r,
                )
            )
        return result

    async def fetch_network_interfaces(self) -> list[NetworkResource]:
        sub_ids = await self._ensure_ready()
        if not sub_ids:
            return []
        raw = await self._run_query("nics", QUERIES["nics"], sub_ids)
        result = []
        for r in raw:
            sub_id = r["subscriptionId"]
            acct_name = self._sub_id_to_name.get(sub_id, "")
            subnet_id = r.get("subnetId", "")
            vnet_name = None
            subnet_name = None
            if subnet_id:
                m = re.search(
                    r"/virtualNetworks/([^/]+)/subnets/([^/]+)",
                    subnet_id,
                    re.IGNORECASE,
                )
                if m:
                    vnet_name = m.group(1)
                    subnet_name = m.group(2)
            result.append(
                NetworkResource(
                    id=f"azure_{sub_id}_{r.get('nicName', '')}",
                    name=r.get("nicName", ""),
                    resource_type="network_interface",
                    provider="azure",
                    account_id=sub_id,
                    account_name=acct_name,
                    region=r.get("location", ""),
                    environment=get_env(acct_name),
                    parent_network=vnet_name,
                    subnet=subnet_name,
                    private_ip=r.get("privateIp"),
                    properties=r,
                )
            )
        return result

    async def fetch_peerings(self) -> list[NetworkPeering]:
        sub_ids = await self._ensure_ready()
        if not sub_ids:
            return []
        raw = await self._run_query("vnets", QUERIES["vnets"], sub_ids)
        peerings: list[NetworkPeering] = []
        seen: set[tuple[str, str]] = set()
        for r in raw:
            if not r.get("peeringName") or not r.get("remoteVnet"):
                continue
            src = f"azure_{r['subscriptionId']}_{r['vnetName']}"
            remote_vnet = ""
            parts = str(r["remoteVnet"]).split("/")
            for i, p in enumerate(parts):
                if p.lower() == "virtualnetworks" and i + 1 < len(parts):
                    remote_vnet = parts[i + 1]
            remote_sub = (
                parts[2]
                if len(parts) > 2 and "/subscriptions/" in r.get("remoteVnet", "")
                else ""
            )
            dst = f"azure_{remote_sub}_{remote_vnet}"
            sorted_pair = sorted([src, dst])
            pair = (sorted_pair[0], sorted_pair[1])
            if pair in seen:
                continue
            seen.add(pair)
            peerings.append(
                NetworkPeering(
                    id=f"peer_{src}_{dst}",
                    name=r.get("peeringName", ""),
                    provider="azure",
                    source_network=src,
                    target_network=dst,
                    state=r.get("peeringState", "Unknown"),
                    source_account=r["subscriptionId"],
                    target_account=remote_sub,
                )
            )
        return peerings

    def get_auth_error(self) -> str | None:
        return self._auth_error

    def set_auth_error(self, error: str | None) -> None:
        self._auth_error = error

    def get_provider_name(self) -> str:
        return "azure"

    def get_discovered_accounts(self) -> dict[str, str]:
        """Return mapping of subscription_id -> display_name."""
        return dict(self._sub_id_to_name)
