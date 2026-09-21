# -*- coding: utf-8 -*-
"""In-process prompt injection — the cron executor path, no HTTP/SSE.

Service chain (verified against qwenpaw 2.2.x):
  app.state.workspace_registry  (_app.py:214)
    .get_loaded_agent(agent_id) / await .get_agent(agent_id)  -> Workspace
      Workspace itself carries stream_query / chat_manager
        (cron executor receives exactly this object as `workspace`)
      ws._service_manager.services.get("channel_manager")   -> ChannelManager
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

from .models import EventRule

logger = logging.getLogger("qwenpaw.event_trigger")


def _status_completed(status: Any) -> bool:
    """Compare robustly: enum or string."""
    if status is None:
        return False
    if status == "completed":
        return True
    return getattr(status, "value", None) == "completed"


def _extract_text(event: Any) -> str:
    """Pull assistant text out of a completed message event."""
    try:
        for item in getattr(event, "output", None) or []:
            if getattr(item, "role", None) != "assistant":
                continue
            for c in getattr(item, "content", None) or []:
                if getattr(c, "type", None) == "text":
                    return getattr(c, "text", "")
    except Exception:
        pass
    return ""


class InProcessInjector:
    """Fires agent reasoning for a rule, in-process, cron-parity semantics."""

    def __init__(self):
        self._registry: Optional[Any] = None

    def _registry_(self) -> Any:
        if self._registry is None:
            from qwenpaw.app._app import app  # platform singleton
            self._registry = app.state.workspace_registry
        return self._registry

    def _workspace(self, agent_id: str) -> Any:
        ws = self._registry_().get_loaded_agent(agent_id)
        if ws is None:
            raise RuntimeError(
                f"workspace for agent '{agent_id}' is not loaded yet"
            )
        return ws

    def _channel_manager(self, ws: Any) -> Any:
        return ws._service_manager.services.get("channel_manager")

    def channel_manager_for(self, agent_id: str) -> Any:
        """Per-workspace channel manager (used by engine notify action too)."""
        return self._channel_manager(self._workspace(agent_id))

    def _session_id(self, rule: EventRule) -> str:
        d = rule.dispatch
        target = d.session_id
        if rule.runtime.share_session:
            return target or f"event:{rule.id}"
        # dedicated accumulating session per rule (cron parity)
        return f"{target}:event:{rule.id}" if target else f"event:{rule.id}"

    async def fire(self, rule: EventRule, prompt: str, out: Dict[str, Any]) -> str:
        """Run one agent turn for the fired event. Returns final text."""
        ws = self._workspace(rule.agent_id)
        cm = self._channel_manager(ws)
        rt = rule.runtime

        req: Dict[str, Any] = {
            "channel": rule.dispatch.channel,
            "user_id": rule.dispatch.user_id,
            "session_id": self._session_id(rule),
            "input": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": prompt}],
                }
            ],
            "session_source": "event-trigger",
            "request_context": {
                "source": "event-trigger",
                "event_rule_id": rule.id,
                # tool approval level follows cron's tool_safety semantics
                **({} if rt.tool_safety else {"approval_level": "off"}),
            },
        }

        # register the chat so it shows up in the console session list
        chat_manager = getattr(ws, "chat_manager", None)
        if chat_manager is not None:
            try:
                await chat_manager.get_or_create_chat(
                    session_id=req["session_id"],
                    user_id=req["user_id"],
                    channel=rule.dispatch.channel,
                    name=rule.name or f"Event: {rule.id}",
                    source="event-trigger",
                )
            except Exception:
                logger.debug("event-trigger: chat spec register failed", exc_info=True)

        final_event: Any = None
        run_id: Optional[str] = None
        baseline_count = 0

        # inbox trace (cron parity): baseline -> create -> append delta -> finalize
        if rt.save_result_to_inbox:
            try:
                from qwenpaw.app.inbox_trace_store import (
                    create_trace,
                    read_session_messages,
                )
                baseline = await read_session_messages(
                    runner=ws,
                    session_id=req["session_id"],
                    user_id=req["user_id"],
                    channel=rule.dispatch.channel,
                )
                baseline_count = len(baseline)
                import uuid as _uuid
                run_id = str(_uuid.uuid4())
                await create_trace(run_id, meta={
                    "task_type": "event",
                    "rule_id": rule.id,
                    "rule_name": rule.name,
                    "dispatch_channel": rule.dispatch.channel,
                    "target_user_id": rule.dispatch.user_id,
                    "target_session_id": req["session_id"],
                    "silent": rt.silent,
                })
            except Exception:
                run_id = None
                logger.debug("event-trigger: trace init failed", exc_info=True)

        async def _run() -> None:
            nonlocal final_event
            async for event in ws.stream_query(req):
                if rt.silent:
                    continue
                if rt.dispatch_mode == "stream":
                    if cm is not None:
                        await cm.send_event(
                            channel=rule.dispatch.channel,
                            user_id=rule.dispatch.user_id,
                            session_id=rule.dispatch.session_id or req["session_id"],
                            event=event,
                            meta={"suppress_console_push": True},
                        )
                elif (
                    getattr(event, "object", None) == "message"
                    and _status_completed(getattr(event, "status", None))
                ):
                    final_event = event

        status = "success"
        try:
            await asyncio.wait_for(_run(), timeout=rt.timeout_seconds)
        except asyncio.TimeoutError:
            status = "timeout"
            raise
        finally:
            if run_id:
                try:
                    from qwenpaw.app.inbox_trace_store import (
                        append_trace_from_session_delta,
                        finalize_trace,
                    )
                    await append_trace_from_session_delta(
                        run_id=run_id,
                        runner=ws,
                        session_id=req["session_id"],
                        user_id=req["user_id"],
                        channel=rule.dispatch.channel,
                        baseline_count=baseline_count,
                    )
                    await finalize_trace(run_id, status=status)
                except Exception:
                    logger.debug("event-trigger: trace finalize failed", exc_info=True)

        if rt.silent:
            return ""
        if final_event is None:
            logger.warning(
                "event-trigger: no completed message in stream rule=%s", rule.id
            )
            return ""
        if cm is not None:
            await cm.send_event(
                channel=rule.dispatch.channel,
                user_id=rule.dispatch.user_id,
                session_id=rule.dispatch.session_id or req["session_id"],
                event=final_event,
                meta={"suppress_console_push": True},
            )
        return _extract_text(final_event)
