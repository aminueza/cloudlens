"""Background fetcher — polls all providers, builds graphs, caches topology."""

import asyncio
import json
import logging
import threading
from datetime import UTC, datetime
from typing import Any

from config.settings import ACCOUNTS, settings
from graph.builder import build_graph, build_structured_graph
from providers.registry import ProviderRegistry

logger = logging.getLogger(__name__)


class BackgroundFetcher:
    """Periodically fetches from all providers, builds graphs, caches results, notifies SSE."""

    def __init__(self, registry: ProviderRegistry, poll_interval: int = 300) -> None:
        self._registry = registry
        self._poll_interval = poll_interval
        self._topology_cache: dict[str, dict[str, Any]] = {}
        self._structured_cache: dict[str, dict[str, Any]] = {}
        self._subscribers: list[asyncio.Queue[str]] = []
        self._lock = threading.Lock()
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._generation = 0

    def get_topology(self, scope: str) -> dict[str, Any] | None:
        with self._lock:
            return self._topology_cache.get(scope)

    def get_structured(self, scope: str) -> dict[str, Any] | None:
        with self._lock:
            return self._structured_cache.get(scope)

    def subscribe(self, queue: asyncio.Queue[str]) -> None:
        with self._lock:
            self._subscribers.append(queue)

    def unsubscribe(self, queue: asyncio.Queue[str]) -> None:
        with self._lock:
            self._subscribers = [q for q in self._subscribers if q is not queue]

    def _notify(self, msg: str) -> None:
        with self._lock:
            dead: list[asyncio.Queue[str]] = []
            for q in self._subscribers:
                try:
                    q.put_nowait(msg)
                except asyncio.QueueFull:
                    dead.append(q)
            for q in dead:
                self._subscribers.remove(q)

    def start(self) -> None:
        self._running = True
        try:
            loop = asyncio.get_running_loop()
            self._task = loop.create_task(self._poll_loop())
            logger.info(
                "Background fetcher started (interval=%ds)", self._poll_interval
            )
        except RuntimeError:
            logger.warning("No running event loop; fetcher will not auto-poll")

    def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            self._task = None
            logger.info("Background fetcher stopped")

    async def _poll_loop(self) -> None:
        await self._fetch_cycle()
        while self._running:
            try:
                await asyncio.sleep(self._poll_interval)
                if not self._running:
                    break
                await self._fetch_cycle()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Fetch cycle failed")

    async def _fetch_cycle(self) -> None:
        """Fetch from all providers, build graphs, cache, notify."""
        try:
            (
                networks,
                networks_sub,
                resources,
                sgs,
                interfaces,
                peerings,
            ) = await self._registry.fetch_all(ACCOUNTS)

            logger.info(
                "Fetched: %d networks, %d resources, %d SGs, %d peerings",
                len(networks),
                len(resources),
                len(sgs),
                len(peerings),
            )

            # Build flat graph for "all" scope
            flat = build_graph("all", networks, resources, sgs, interfaces, peerings)
            structured = build_structured_graph(
                "all", networks, networks_sub, resources, sgs, interfaces, peerings
            )

            with self._lock:
                self._topology_cache["all"] = flat
                self._structured_cache["all"] = structured

            self._generation += 1

            # Post-fetch: save snapshot, health checks, etc.
            await self._post_fetch("all", structured)

            self._notify(
                json.dumps(
                    {
                        "type": "update",
                        "scope": "all",
                        "generation": self._generation,
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                )
            )

            logger.info(
                "Fetch cycle %d complete: %d networks, %d peerings",
                self._generation,
                structured.get("stats", {}).get("networks", 0),
                structured.get("stats", {}).get("peerings", 0),
            )

        except Exception:
            logger.exception("Fetch cycle failed")
            self._notify(
                json.dumps(
                    {
                        "type": "auth_error",
                        "errors": self._registry.get_auth_errors(),
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                )
            )

    async def _post_fetch(self, scope: str, structured: dict[str, Any]) -> None:
        """Save snapshot, detect changes, run health checks."""
        snapshot_id = None

        # Save snapshot
        try:
            from db import repository as repo

            snapshot_id = await repo.save_snapshot(
                scope=scope,
                graph_json=json.dumps(structured),
                structured_json=json.dumps(structured),
            )
        except Exception:
            logger.debug("Could not save snapshot for %s", scope, exc_info=True)

        # Change detection (diff against previous snapshot)
        if snapshot_id is not None:
            try:
                from db import repository as repo
                from engine.diff import compute_diff

                prev = await repo.get_previous_snapshot(scope, snapshot_id)
                if prev:
                    prev_json = prev.get(
                        "structured_json", prev.get("graph_json", "{}")
                    )
                    prev_structured = (
                        json.loads(prev_json)
                        if isinstance(prev_json, str)
                        else prev_json
                    )
                    changes = compute_diff(
                        scope, prev_structured, structured, snapshot_id
                    )
                    if changes:
                        await repo.save_changes(changes)
                        logger.info("Detected %d changes for %s", len(changes), scope)
            except Exception:
                logger.debug("Change detection failed for %s", scope, exc_info=True)

        # Health checks
        try:
            from db import repository as repo
            from engine.health import run_health_checks

            checks = run_health_checks(scope, structured)
            if checks:
                await repo.save_health_checks(checks)
        except Exception:
            logger.debug("Health checks failed for %s", scope, exc_info=True)

        # Compliance
        try:
            from db import repository as repo
            from engine.compliance import evaluate_rules

            rules = await repo.list_compliance_rules(scope)
            violations = evaluate_rules(scope, structured, rules)
            await repo.clear_violations(scope)
            if violations:
                await repo.save_violations(violations)
        except Exception:
            logger.debug("Compliance check failed for %s", scope, exc_info=True)

        # Cleanup
        try:
            from db import repository as repo

            await repo.cleanup_old_snapshots(scope, keep=settings.SNAPSHOT_RETENTION)
        except Exception:
            logger.debug("Snapshot cleanup failed for %s", scope, exc_info=True)
