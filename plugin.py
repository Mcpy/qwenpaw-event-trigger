# -*- coding: utf-8 -*-
"""Event Trigger plugin entry.

Wires: Repo(events.json) + Engine(per-rule loops) + InProcessInjector +
RuleManager(registration gate) + REST router under /api/events.

The engine is the event-driven twin of the cron subsystem: time-driven
ScheduleSpec is replaced by a poll + checker-script condition layer;
dispatch / runtime semantics intentionally mirror app/crons.
"""

from __future__ import annotations

import asyncio
import logging
import os

from qwenpaw.constant import WORKING_DIR
from qwenpaw.plugins.api import PluginApi

from qwenpaw_event_trigger.api import build_router
from qwenpaw_event_trigger.engine import Engine
from qwenpaw_event_trigger.injector import InProcessInjector
from qwenpaw_event_trigger.manager import RuleManager
from qwenpaw_event_trigger.repo import Repo

logger = logging.getLogger(__name__)

DATA_DIR = str(WORKING_DIR / "event_trigger")


class EventTriggerPlugin:
    def __init__(self) -> None:
        self.engine: Engine | None = None

    def register(self, api: PluginApi) -> None:
        repo = Repo(DATA_DIR)
        injector = InProcessInjector()
        self.engine = Engine(repo=repo, injector=injector)
        manager = RuleManager(engine=self.engine, repo=repo, data_dir=DATA_DIR)
        engine = self.engine

        async def _startup() -> None:
            # channel_manager is resolved per-workspace at fire time
            # (ws._service_manager.services); nothing to attach here.
            await engine.start()

        def _shutdown() -> None:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(engine.stop())
            else:
                loop.run_until_complete(engine.stop())

        api.register_startup_hook(hook_name="event_trigger_start", callback=_startup)
        api.register_shutdown_hook(hook_name="event_trigger_stop", callback=_shutdown)
        api.register_http_router(
            build_router(manager, repo, injector=injector), prefix="/events"
        )
        logger.info(
            "✓ event-trigger registered (data dir: %s, rules: %d)",
            DATA_DIR,
            len(repo.load().rules),
        )


plugin = EventTriggerPlugin()
