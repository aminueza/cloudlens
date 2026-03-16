"""AWS provider — queries EC2/VPC APIs and normalizes to common schema."""

import asyncio
import logging
from typing import Any

from providers.base import NetworkPeering, NetworkResource, ProviderInterface

logger = logging.getLogger(__name__)

_DEFAULT_REGIONS = ["us-east-1", "us-west-2", "eu-west-1", "eu-central-1"]


def _aws_tags_to_dict(tags: list[dict] | None) -> dict[str, str]:
    if not tags:
        return {}
    return {t["Key"]: t["Value"] for t in tags if "Key" in t and "Value" in t}


def _get_tag(tags: dict[str, str], key: str, default: str = "") -> str:
    return tags.get(key, tags.get(key.lower(), default))


class AWSProvider(ProviderInterface):
    def __init__(self) -> None:
        self._auth_error: str | None = None
        self._regions: list[str] = []
        self._account_id: str = ""

    def _get_session(self):
        try:
            import boto3

            return boto3.Session()
        except ImportError:
            self._auth_error = "boto3 not installed. Run: pip install cloudlens[aws]"
            raise
        except Exception as e:
            self._auth_error = f"AWS auth failed: {e}"
            raise

    def _get_client(self, service: str, region: str):
        session = self._get_session()
        return session.client(service, region_name=region)

    def _discover(self) -> None:
        """Discover AWS account ID and available regions."""
        if self._regions:
            return
        try:
            session = self._get_session()
            # Get account ID via STS
            sts = session.client("sts")
            identity = sts.get_caller_identity()
            self._account_id = identity.get("Account", "")
            # Discover enabled regions
            ec2 = session.client("ec2", region_name="us-east-1")
            response = ec2.describe_regions(
                Filters=[
                    {
                        "Name": "opt-in-status",
                        "Values": ["opt-in-not-required", "opted-in"],
                    }
                ]
            )
            self._regions = [r["RegionName"] for r in response.get("Regions", [])]
            if not self._regions:
                self._regions = list(_DEFAULT_REGIONS)
            logger.info(
                "Discovered AWS account %s with %d regions",
                self._account_id,
                len(self._regions),
            )
        except Exception as e:
            logger.warning("AWS discovery failed, using defaults: %s", e)
            self._regions = list(_DEFAULT_REGIONS)

    async def _describe(
        self, service: str, region: str, method: str, key: str, **kwargs: Any
    ) -> list[dict[str, Any]]:
        try:
            client = await asyncio.to_thread(self._get_client, service, region)
            fn = getattr(client, method)
            result = await asyncio.to_thread(fn, **kwargs)
            self._auth_error = None
            items: list[dict[str, Any]] = result.get(key, [])
            return items
        except Exception as e:
            msg = str(e).lower()
            if (
                "credential" in msg
                or "token" in msg
                or "expired" in msg
                or "not authorized" in msg
            ):
                self._auth_error = f"AWS auth failed in {region}: {e}"
                logger.error("AWS auth error: %s", self._auth_error)
            else:
                logger.warning("AWS %s.%s failed in %s: %s", service, method, region, e)
            return []

    def _get_env(self, tags: dict[str, str], acct_name: str = "") -> str:
        env = _get_tag(tags, "Environment", "").lower()
        if env in ("dev", "stg", "prd", "global"):
            return env
        from config.settings import get_env

        return get_env(acct_name)

    async def fetch_networks(self) -> list[NetworkResource]:
        await asyncio.to_thread(self._discover)
        results: list[NetworkResource] = []

        async def _fetch_region(region: str) -> None:
            vpcs = await self._describe("ec2", region, "describe_vpcs", "Vpcs")
            for vpc in vpcs:
                tags = _aws_tags_to_dict(vpc.get("Tags"))
                name = _get_tag(tags, "Name", vpc["VpcId"])
                results.append(
                    NetworkResource(
                        id=f"aws_{vpc['VpcId']}",
                        name=name,
                        resource_type="virtual_network",
                        provider="aws",
                        account_id=vpc.get("OwnerId", self._account_id),
                        account_name=_get_tag(tags, "Name", ""),
                        region=region,
                        environment=self._get_env(tags),
                        address_space=[vpc.get("CidrBlock", "")],
                        tags=tags,
                        provisioning_state=(
                            "active"
                            if vpc.get("State") == "available"
                            else vpc.get("State", "")
                        ),
                        properties=vpc,
                    )
                )

        await asyncio.gather(*[_fetch_region(r) for r in self._regions])
        return results

    async def fetch_networks_with_subnets(self) -> list[NetworkResource]:
        results: list[NetworkResource] = []

        async def _fetch_region(region: str) -> None:
            subnets = await self._describe("ec2", region, "describe_subnets", "Subnets")
            for s in subnets:
                tags = _aws_tags_to_dict(s.get("Tags"))
                results.append(
                    NetworkResource(
                        id=f"aws_{s['SubnetId']}",
                        name=_get_tag(tags, "Name", s["SubnetId"]),
                        resource_type="virtual_network",
                        provider="aws",
                        account_id=s.get("OwnerId", self._account_id),
                        account_name="",
                        region=region,
                        environment=self._get_env(tags),
                        address_space=[s.get("CidrBlock", "")],
                        parent_network=s.get("VpcId"),
                        subnet=_get_tag(tags, "Name", s["SubnetId"]),
                        properties=s,
                        tags=tags,
                    )
                )

        await asyncio.gather(*[_fetch_region(r) for r in self._regions])
        return results

    async def fetch_resources(self) -> list[NetworkResource]:
        results: list[NetworkResource] = []

        async def _fetch_region(region: str) -> None:
            # NAT Gateways
            nats = await self._describe(
                "ec2", region, "describe_nat_gateways", "NatGateways"
            )
            for n in nats:
                tags = _aws_tags_to_dict(n.get("Tags"))
                results.append(
                    NetworkResource(
                        id=f"aws_{n['NatGatewayId']}",
                        name=_get_tag(tags, "Name", n["NatGatewayId"]),
                        resource_type="nat_gateway",
                        provider="aws",
                        account_id=self._account_id,
                        account_name="",
                        region=region,
                        environment=self._get_env(tags),
                        parent_network=n.get("VpcId"),
                        subnet=n.get("SubnetId"),
                        provisioning_state=n.get("State", ""),
                        tags=tags,
                        properties=n,
                    )
                )
            # Elastic IPs
            eips = await self._describe(
                "ec2", region, "describe_addresses", "Addresses"
            )
            for eip in eips:
                tags = _aws_tags_to_dict(eip.get("Tags"))
                results.append(
                    NetworkResource(
                        id=f"aws_{eip.get('AllocationId', '')}",
                        name=_get_tag(tags, "Name", eip.get("PublicIp", "")),
                        resource_type="public_ip",
                        provider="aws",
                        account_id=self._account_id,
                        account_name="",
                        region=region,
                        environment=self._get_env(tags),
                        private_ip=eip.get("PrivateIpAddress"),
                        tags=tags,
                        properties=eip,
                    )
                )
            # VPN Gateways
            vpngws = await self._describe(
                "ec2", region, "describe_vpn_gateways", "VpnGateways"
            )
            for gw in vpngws:
                tags = _aws_tags_to_dict(gw.get("Tags"))
                vpc_id = None
                attachments = gw.get("VpcAttachments", [])
                if attachments:
                    vpc_id = attachments[0].get("VpcId")
                results.append(
                    NetworkResource(
                        id=f"aws_{gw['VpnGatewayId']}",
                        name=_get_tag(tags, "Name", gw["VpnGatewayId"]),
                        resource_type="vpn_gateway",
                        provider="aws",
                        account_id=self._account_id,
                        account_name="",
                        region=region,
                        environment=self._get_env(tags),
                        parent_network=vpc_id,
                        provisioning_state=gw.get("State", ""),
                        tags=tags,
                        properties=gw,
                    )
                )

        await asyncio.gather(*[_fetch_region(r) for r in self._regions])
        return results

    async def fetch_security_groups(self) -> list[NetworkResource]:
        results: list[NetworkResource] = []

        async def _fetch_region(region: str) -> None:
            sgs = await self._describe(
                "ec2", region, "describe_security_groups", "SecurityGroups"
            )
            for sg in sgs:
                tags = _aws_tags_to_dict(sg.get("Tags"))
                rules = len(sg.get("IpPermissions", [])) + len(
                    sg.get("IpPermissionsEgress", [])
                )
                results.append(
                    NetworkResource(
                        id=f"aws_{sg['GroupId']}",
                        name=sg.get("GroupName", sg["GroupId"]),
                        resource_type="security_group",
                        provider="aws",
                        account_id=sg.get("OwnerId", self._account_id),
                        account_name="",
                        region=region,
                        environment=self._get_env(tags),
                        parent_network=sg.get("VpcId"),
                        rules_count=rules,
                        tags=tags,
                        properties=sg,
                    )
                )

        await asyncio.gather(*[_fetch_region(r) for r in self._regions])
        return results

    async def fetch_network_interfaces(self) -> list[NetworkResource]:
        results: list[NetworkResource] = []

        async def _fetch_region(region: str) -> None:
            enis = await self._describe(
                "ec2", region, "describe_network_interfaces", "NetworkInterfaces"
            )
            for eni in enis:
                tags = _aws_tags_to_dict(eni.get("TagSet", eni.get("Tags")))
                ip = ""
                if eni.get("PrivateIpAddresses"):
                    ip = eni["PrivateIpAddresses"][0].get("PrivateIpAddress", "")
                results.append(
                    NetworkResource(
                        id=f"aws_{eni['NetworkInterfaceId']}",
                        name=_get_tag(tags, "Name", eni["NetworkInterfaceId"]),
                        resource_type="network_interface",
                        provider="aws",
                        account_id=eni.get("OwnerId", self._account_id),
                        account_name="",
                        region=region,
                        environment=self._get_env(tags),
                        parent_network=eni.get("VpcId"),
                        subnet=eni.get("SubnetId"),
                        private_ip=ip,
                        tags=tags,
                        properties=eni,
                    )
                )

        await asyncio.gather(*[_fetch_region(r) for r in self._regions])
        return results

    async def fetch_peerings(self) -> list[NetworkPeering]:
        results: list[NetworkPeering] = []
        seen: set[str] = set()

        async def _fetch_region(region: str) -> None:
            peers = await self._describe(
                "ec2",
                region,
                "describe_vpc_peering_connections",
                "VpcPeeringConnections",
            )
            for p in peers:
                pid = p["VpcPeeringConnectionId"]
                if pid in seen:
                    continue
                seen.add(pid)
                tags = _aws_tags_to_dict(p.get("Tags"))
                status = p.get("Status", {}).get("Code", "unknown")
                state = "connected" if status == "active" else status
                req = p.get("RequesterVpcInfo", {})
                acc = p.get("AccepterVpcInfo", {})
                results.append(
                    NetworkPeering(
                        id=f"aws_{pid}",
                        name=_get_tag(tags, "Name", pid),
                        provider="aws",
                        source_network=f"aws_{req.get('VpcId', '')}",
                        target_network=f"aws_{acc.get('VpcId', '')}",
                        state=state,
                        source_account=req.get("OwnerId", ""),
                        target_account=acc.get("OwnerId", ""),
                    )
                )

        await asyncio.gather(*[_fetch_region(r) for r in self._regions])
        return results

    def get_auth_error(self) -> str | None:
        return self._auth_error

    def set_auth_error(self, error: str | None) -> None:
        self._auth_error = error

    def get_provider_name(self) -> str:
        return "aws"

    def get_discovered_accounts(self) -> dict[str, str]:
        if self._account_id:
            return {self._account_id: f"aws-{self._account_id}"}
        return {}
