# -*- coding: utf-8 -*-
"""Scheduling engine: one asyncio loop per rule.

check(interval) -> script -> hysteresis/cooldown gate -> action(notify|agent)
State transitions are persisted after every run; failures never fire and
never crash the loop.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import time
from typing import Any, Dict

from .models import (
    ActionKind,
    AuditKind,
    AuditRecord,
    EventRule,
    EventsFile,
    RunRecord,
    RuleState,
)
from .protocol import ProtocolError, run_script

logger = logging.getLogger("qwenpaw.event_trigger")

_SCRIPT_ERRORS = (ProtocolError, subprocess.SubprocessError, TimeoutError, OSError)


class Engine:
    def __init__(self, repo, injector, channel_manager=None):
        self._repo = repo
        self._injector = injector          # .fire(rule, prompt, out) coroutine
        self._channel_manager = channel_manager  # may be attached later
        self._events: EventsFile = repo.load()
        self._tasks: Dict[str, asyncio.Task] = {}

    # ---- lifecycle ----

    @property
    def events(self) -> EventsFile:
        return self._events

    async def start(self) -> None:
        for rule in self._events.rules:
            if rule.enabled:
                self._spawn(rule)
        logger.info("event-trigger: started %d rule(s)", len(self._tasks))

    async def stop(self) -> None:
        for t in self._tasks.values():
            t.cancel()
        self._tasks.clear()

    def _spawn(self, rule: EventRule) -> None:
        old = self._tasks.pop(rule.id, None)
        if old:
            old.cancel()
        self._tasks[rule.id] = asyncio.create_task(
            self._loop(rule.id), name=f"event-trigger:{rule.id}"
        )

    # ---- rule mutations (called by manager/api) ----

    async def upsert_rule(self, rule: EventRule, *, audit_detail: str = "") -> None:
        rule.updated_at = time.time()
        existing = self._events.get(rule.id)
        if existing:
            self._events.rules.remove(existing)
        self._events.rules.append(rule)
        self._events.states.setdefault(rule.id, RuleState())
        await self._repo.save(self._events)
        kind = AuditKind.update if existing else AuditKind.register
        await self._repo.append_audit(
            AuditRecord(kind=kind, rule_id=rule.id, name=rule.name, detail=audit_detail)
        )
        if rule.enabled:
            self._spawn(rule)
        else:
            self._drop_task(rule.id)

    async def set_enabled(self, rule_id: str, enabled: bool):
        rule = self._events.get(rule_id)
        if not rule:
            return None
        rule.enabled = enabled
        rule.updated_at = time.time()
        await self._repo.save(self._events)
        await self._repo.append_audit(
            AuditRecord(
                kind=AuditKind.enable if enabled else AuditKind.disable,
                rule_id=rule_id,
                name=rule.name,
            )
        )
        if enabled:
            # new monitoring round: per-round fire counter resets here
            self._events.states[rule_id] = RuleState()  # fresh round: counter + state reset
            await self._repo.save(self._events)
            self._spawn(rule)
        else:
            self._drop_task(rule_id)
        return rule

    async def delete_rule(self, rule_id: str):
        rule = self._events.get(rule_id)
        if not rule:
            return None
        self._events.rules.remove(rule)
        self._events.states.pop(rule_id, None)
        await self._repo.save(self._events)
        await self._repo.append_audit(
            AuditRecord(kind=AuditKind.delete, rule_id=rule_id, name=rule.name)
        )
        self._drop_task(rule_id)
        return rule

    def _drop_task(self, rule_id: str) -> None:
        t = self._tasks.pop(rule_id, None)
        if t:
            t.cancel()

    # ---- the loop ----

    async def _loop(self, rule_id: str) -> None:
        while True:
            rule = self._events.get(rule_id)
            if rule is None or not rule.enabled:
                return
            try:
                fired = await self._check_once(rule)
                if fired:
                    rule = self._events.get(rule_id)
                    st = self._events.states.get(rule_id)
                    mx = rule.runtime.max_triggers if rule else 0
                    if rule and mx > 0 and st and st.trigger_count >= mx:
                        await self._repo.append_run(
                            RunRecord(rule_id=rule_id, kind="skipped",
                                      detail=f"auto-disabled: reached max_triggers({mx})")
                        )
                        await self._repo.append_audit(
                            AuditRecord(kind=AuditKind.disable, rule_id=rule_id,
                                        name=rule.name,
                                        detail=f"auto: reached max_triggers({mx})")
                        )
                        rule.enabled = False
                        await self._repo.save(self._events)
                        self._drop_task(rule_id)
                        return
            except asyncio.CancelledError:
                raise
            except Exception as e:  # never die
                logger.warning("event-trigger: loop error rule=%s: %r", rule_id, e)
                st = self._events.states.setdefault(rule_id, RuleState())
                st.last_error = repr(e)
                await self._repo.save(self._events)
            await asyncio.sleep(rule.poll.interval_seconds)

    async def _check_once(self, rule: EventRule) -> bool:
        st = self._events.states.setdefault(rule.id, RuleState())
        started = time.time()
        try:
            out, _duration = await asyncio.to_thread(
                run_script,
                rule.script.path,
                st.state,
                rule.id,
                rule.name,
                rule.script.interpreter,
                rule.runtime.script_timeout_seconds,
                rule.script.content_hash,
            )
        except _SCRIPT_ERRORS as e:
            st.last_error = str(e)
            st.run_count += 1
            await self._repo.append_run(
                RunRecord(rule_id=rule.id, kind="error", ok=False,
                          duration_ms=int((time.time() - started) * 1000),
                          detail=str(e))
            )
            await self._repo.save(self._events)
            return

        st.run_count += 1
        st.last_run_at = started
        st.last_error = None
        if isinstance(out.get("state"), dict):
            st.state = out["state"]  # script-owned; keep old when absent

        fired = False
        if out.get("triggered"):
            cd = int(out.get("cooldown", rule.runtime.cooldown_seconds))
            now = time.time()
            if st.last_triggered_at and cd and (now - st.last_triggered_at) < cd:
                await self._repo.append_run(
                    RunRecord(rule_id=rule.id, kind="skipped", detail="cooldown")
                )
            else:
                fired = True
                st.trigger_count += 1
                st.last_triggered_at = now

        await self._repo.save(self._events)
        await self._repo.append_run(
            RunRecord(rule_id=rule.id,
                      kind="trigger" if fired else "check",
                      ok=True,
                      duration_ms=int((time.time() - started) * 1000),
                      detail=(out.get("title") or "")[:200])
        )
        if fired:
            await self._fire(rule, out)
        return fired

    # ---- actions ----

    def _render(self, template: str, out: Dict[str, Any]) -> str:
        return template.format(
            title=out.get("title") or "event",
            event=out.get("event") or "",
        )

    async def _fire(self, rule: EventRule, out: Dict[str, Any]) -> None:
        title = out.get("title") or "event"
        try:
            if rule.action == ActionKind.notify:
                await self._notify(rule, self._render(rule.notify_template, out))
            else:
                prompt = self._render(rule.prompt_template, out)
                await self._injector.fire(rule, prompt, out)
            logger.info("event-trigger: fired rule=%s title=%s", rule.id, title)
        except Exception as e:
            logger.warning("event-trigger: fire failed rule=%s: %r", rule.id, e)
            await self._repo.append_run(
                RunRecord(rule_id=rule.id, kind="error", ok=False, detail=f"fire: {e!r}")
            )

    async def _notify(self, rule: EventRule, text: str) -> None:
        # per-workspace resolution, same as agent action — no engine-level handle
        cm = self._injector.channel_manager_for(rule.agent_id)
        if cm is None:
            raise RuntimeError(
                f"channel_manager unavailable for agent '{rule.agent_id}'"
            )
        await cm.send_text(
            channel=rule.dispatch.channel,
            user_id=rule.dispatch.user_id,
            session_id=rule.dispatch.session_id or f"event:{rule.id}",
            text=text,
            meta={"suppress_console_push": False},
        )
