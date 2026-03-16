"""Background fetcher — polls all providers, caches topology, runs post-fetch tasks."""

import asyncio
import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any

from config.settings import settings
from providers.registry import AuthenticationError, ProviderRegistry

logger = logging.getLogger(__name__)


class BackgroundFetcher:
    """Periodically fetches topology from all providers via the registry.

    Caches flat and structured topology per scope. After each fetch cycle,
    saves snapshots, runs diff/health/compliance. Manages SSE subscribers
    for live update notifications.
    """

    def __init__(self, registry: ProviderRegistry, poll_interval: int = 60) -> None:
        self._registry = registry
        self._poll_interval = poll_interval
        self._topology_cache: dict[str, dict[str, Any]] = {}
        self._structured_cache: dict[str, dict[str, Any]] = {}
        self._subscribers: list[asyncio.Queue[str]] = []
        self._lock = threading.Lock()
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._auth_errors: dict[str, str] = {}

    # --- Cache access ---

    def get_topology(self, scope: str) -> dict[str, Any] | None:
        """Return cached flat topology for the given scope."""
        with self._lock:
            return self._topology_cache.get(scope)

    def get_structured(self, scope: str) -> dict[str, Any] | None:
        """Return cached structured topology for the given scope."""
        with self._lock:
            return self._structured_cache.get(scope)

    # --- SSE subscriber management ---

    def subscribe(self, queue: asyncio.Queue[str]) -> None:
        """Register an SSE subscriber."""
        with self._lock:
            self._subscribers.append(queue)

    def unsubscribe(self, queue: asyncio.Queue[str]) -> None:
        """Remove an SSE subscriber."""
        with self._lock:
            self._subscribers = [q for q in self._subscribers if q is not queue]

    def _notify(self, event: dict[str, Any]) -> None:
        """Send an event to all SSE subscribers."""
        payload = json.dumps(event)
        with self._lock:
            dead: list[asyncio.Queue[str]] = []
            for q in self._subscribers:
                try:
                    q.put_nowait(payload)
                except asyncio.QueueFull:
                    dead.append(q)
            for q in dead:
                self._subscribers.remove(q)

    # --- Lifecycle ---

    def start(self) -> None:
        """Start the background polling loop."""
        self._running = True
        try:
            loop = asyncio.get_running_loop()
            self._loop = loop
            self._task = loop.create_task(self._poll_loop())
        except RuntimeError:
            logger.warning("No running event loop; fetcher will not auto-poll")

    def stop(self) -> None:
        """Stop the background polling loop."""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            self._task = None

    # --- Polling ---

    async def _poll_loop(self) -> None:
        """Main polling loop."""
        # Initial fetch immediately
        await self._fetch_all()

        while self._running:
            try:
                await asyncio.sleep(self._poll_interval)
                if not self._running:
                    break
                await self._fetch_all()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in fetch loop")

    async def _fetch_all(self) -> None:
        """Fetch topology from all providers for all scopes."""
        scopes = self._registry.get_scopes()

        for scope in scopes:
            await self._fetch_scope(scope)

        # Also fetch the "all" aggregate
        if "all" not in scopes:
            await self._fetch_scope("all")

    async def _fetch_scope(self, scope: str) -> None:
        """Fetch and cache topology for a single scope."""
        try:
            topology = await self._registry.fetch_topology(scope)
            structured = await self._registry.fetch_structured(scope)

            with self._lock:
                old_topology = self._topology_cache.get(scope)
                self._topology_cache[scope] = topology
                self._structured_cache[scope] = structured

            # Clear auth errors for providers that succeeded
            for name in self._registry.providers:
                if name in self._auth_errors:
                    del self._auth_errors[name]

            # Post-fetch tasks
            await self._post_fetch(scope, topology, structured, old_topology)

            # Notify SSE subscribers
            self._notify(
                {
                    "type": "update",
                    "scope": scope,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "node_count": len(topology.get("nodes", [])),
                }
            )

        except AuthenticationError as exc:
            provider = getattr(exc, "provider", "unknown")
            error_msg = str(exc)
            self._auth_errors[provider] = error_msg
            logger.warning(
                "Auth error for provider %s in scope %s: %s", provider, scope, exc
            )

            self._notify(
                {
                    "type": "auth_error",
                    "scope": scope,
                    "provider": provider,
                    "error": error_msg,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

        except Exception:
            logger.exception("Failed to fetch scope %s", scope)

    async def _post_fetch(
        self,
        scope: str,
        topology: dict[str, Any],
        structured: dict[str, Any],
        old_topology: dict[str, Any] | None,
    ) -> None:
        """Run post-fetch tasks: snapshot, diff, health checks, compliance."""
        try:

            from db import repository as repo

            await repo.save_snapshot(
                scope=scope, generation=0, topology=topology, structured=topology
            )
        except Exception:
            logger.debug("Could not save snapshot for %s", scope, exc_info=True)

        # Diff detection
        if old_topology is not None:
            try:
                from engine.diff import compute_diff

                changes = compute_diff(old_topology, topology)
                if changes:

                    from db import repository as repo

                    await repo.save_changes(changes)
                    logger.info("Detected %d changes in scope %s", len(changes), scope)
            except Exception:
                logger.debug("Could not compute diff for %s", scope, exc_info=True)

        # Health checks
        try:
            from engine.health import run_health_checks

            run_health_checks(structured, scope)
        except Exception:
            logger.debug("Could not run health checks for %s", scope, exc_info=True)

        # Compliance evaluation
        try:
            from engine.compliance import evaluate_compliance

            evaluate_compliance(structured, scope)
        except Exception:
            logger.debug("Could not evaluate compliance for %s", scope, exc_info=True)

        # Snapshot retention cleanup
        try:

            from db import repository as repo

            await repo.cleanup_old_snapshots(scope, keep=settings.SNAPSHOT_RETENTION)
        except Exception:
            logger.debug("Could not clean up snapshots for %s", scope, exc_info=True)
