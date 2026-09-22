# -*- coding: utf-8 -*-
"""Event Trigger plugin entry (v0.3 — per-agent, cron-aligned).

Each loaded agent workspace owns its own Engine/Manager/Repo triple with data
under ``workspace_dir/event_trigger`` — the same shape as cron's
``workspace_dir/jobs.json``.  The REST router is stateless and dispatches per
request via ``resolve_bundle(agent_id)`` (lazy-loads the workspace like the
cron router's ``get_agent_for_request``).

Wiring: Repo + Engine(per-rule loops) + InProcessInjector + RuleManager,
per agent.  Legacy global data (v0.2 ``WORKING_DIR/event_trigger``) is
migrated automatically (see migration.py).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from qwenpaw.constant import WORKING_DIR
from qwenpaw.plugins.api import PluginApi

from qwenpaw_event_trigger.api import build_router
from qwenpaw_event_trigger.engine import Engine
from qwenpaw_event_trigger.injector import InProcessInjector
from qwenpaw_event_trigger.manager import RuleManager
from qwenpaw_event_trigger.repo import Repo

logger = logging.getLogger("qwenpaw.event_trigger")

LEGACY_DATA_DIR = str(WORKING_DIR / "event_trigger")


@dataclass
class Bundle:
    """Per-agent engine triple + the workspace it lives in."""

    agent_id: str
    workspace: object
    repo: Repo
    engine: Engine
    manager: RuleManager


class EventTriggerPlugin:
    def __init__(self) -> None:
        self.injector = InProcessInjector()
        self._bundles: dict[str, Bundle] = {}

    # ---- per-agent resolution (stateless dispatch, cron parity) ----

    def _registry(self):
        from qwenpaw.app._app import app  # platform singleton
        return app.state.workspace_registry

    async def resolve_bundle(self, agent_id: str) -> Bundle:
        """Return the agent's engine bundle, creating it on first use.

        Loads the workspace lazily (cron-parity with get_agent_for_request);
        migrates any legacy rules owned by this agent before its engine
        starts.
        """
        bundle = self._bundles.get(agent_id)
        if bundle is not None:
            return bundle

        registry = self._registry()
        ws = registry.get_loaded_agent(agent_id)
        if ws is None:
            ws = await registry.get_agent(agent_id)  # lazy-load + 404 unknown
        bundle = self._build_bundle(agent_id, ws)
        self._bundles[agent_id] = bundle

        # lazy legacy migration (loaded agents were migrated at startup)
        from qwenpaw_event_trigger import migration
        if migration.legacy_exists(LEGACY_DATA_DIR):
            moved = await migration.migrate_agent(
                LEGACY_DATA_DIR, agent_id, ws.workspace_dir,
            )
            if moved:
                # refresh in-memory state with what migration brought in
                bundle.engine._events = bundle.repo.load()
        if bundle.engine._tasks == {}:
            await bundle.engine.start()
        return bundle

    def _build_bundle(self, agent_id: str, ws) -> Bundle:
        data_dir = os.path.join(ws.workspace_dir, "event_trigger")
        repo = Repo(data_dir)
        engine = Engine(repo=repo, injector=self.injector, agent_id=agent_id)
        manager = RuleManager(engine=engine, repo=repo, data_dir=data_dir)
        return Bundle(agent_id=agent_id, workspace=ws, repo=repo,
                      engine=engine, manager=manager)

    # ---- plugin lifecycle ----

    def register(self, api: PluginApi) -> None:
        async def _startup() -> None:
            # channel_manager is resolved per-workspace at fire time
            # (ws._service_manager.services); nothing to attach here.
            # Re-entry guard: hot-reinstall can leave the previous engine's
            # loops alive (module reload resets globals). Kill by task name.
            import asyncio as _asyncio
            for t in _asyncio.all_tasks():
                if t.get_name().startswith("event-trigger:"):
                    t.cancel()

            # eager migration + engine start for currently loaded agents
            registry = self._registry()
            loaded_dirs = {
                aid: registry.get_loaded_agent(aid).workspace_dir
                for aid in registry.list_loaded_agents()
            }
            for agent_id, ws_dir in loaded_dirs.items():
                try:
                    await self.resolve_bundle(agent_id)
                except Exception:
                    logger.warning(
                        "event-trigger: bundle for '%s' failed to start",
                        agent_id, exc_info=True,
                    )

            from qwenpaw_event_trigger import migration
            migration.archive_legacy_if_done(LEGACY_DATA_DIR, loaded_dirs)

            removed = self._gc_all()
            if removed:
                logger.info("event-trigger: GC removed %d orphan script(s)",
                            removed)
            total = sum(len(b.engine._tasks) for b in self._bundles.values())
            logger.info("event-trigger: started %d loop(s) across %d agent(s)",
                        total, len(self._bundles))

        def _shutdown() -> None:
            # synchronous, name-based cancel — create_task(engine.stop()) races
            # with uninstall (new engine spawns before old loops actually die)
            import asyncio as _asyncio
            for t in _asyncio.all_tasks():
                if t.get_name().startswith("event-trigger:"):
                    t.cancel()
            for bundle in self._bundles.values():
                bundle.engine._tasks.clear()

        api.register_startup_hook(hook_name="event_trigger_start",
                                  callback=_startup)
        api.register_shutdown_hook(hook_name="event_trigger_stop",
                                   callback=_shutdown)
        api.register_http_router(
            build_router(self.resolve_bundle, injector=self.injector),
            prefix="/events",
        )
        api.register_skill_provider(
            skills_dir=Path(__file__).parent / "skills",
            enabled_by_default=True,
            channels=["all"],
        )
        legacy = migration_summary(LEGACY_DATA_DIR)
        logger.info("✓ event-trigger v0.3 registered (per-agent scope; "
                    "legacy dir: %s%s)",
                    LEGACY_DATA_DIR,
                    f", {legacy} rule(s) pending migration" if legacy else "")

    def _gc_all(self) -> int:
        removed = 0
        for bundle in self._bundles.values():
            try:
                removed += bundle.manager.gc_orphan_scripts()
            except Exception:
                logger.debug("event-trigger: GC failed for %s",
                             bundle.agent_id, exc_info=True)
        return removed


def migration_summary(legacy_dir: str) -> int:
    from qwenpaw_event_trigger import migration
    legacy = migration.load_legacy_events(legacy_dir)
    return len(legacy.rules) if legacy is not None else 0


plugin = EventTriggerPlugin()
