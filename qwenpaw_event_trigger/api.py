# -*- coding: utf-8 -*-
"""REST API under /api/events (FastAPI APIRouter, mounted by the plugin).

v0.3 — agent-scoped, aligned with the cron subsystem's URL shape:

    GET  /api/events/{agent_id}/                      list rules
    POST /api/events/{agent_id}/                      create (body = RegisterBody)
    PUT  /api/events/{agent_id}/{rule_id}             update
    DEL  /api/events/{agent_id}/{rule_id}             delete
    POST /api/events/{agent_id}/{rule_id}/enable      enable  (= register)
    POST /api/events/{agent_id}/{rule_id}/disable     disable
    POST /api/events/{agent_id}/{rule_id}/run         fire one check now
    GET  /api/events/{agent_id}/{rule_id}/runs        run history
    GET  /api/events/{agent_id}/audit/recent          audit trail
    GET  /api/events/{agent_id}/dispatch-targets      chat targets for the form

Global (agent-independent) resources stay unscoped:
    GET /api/events/templates     bundled checker templates
    GET /api/events/protocol      script protocol doc

``resolve_bundle(agent_id)`` (provided by plugin.py) resolves the agent's
workspace (lazy-loading it when needed), migrates any legacy rules, and
returns that agent's own Engine/Manager/Repo — the same stateless
per-request dispatch pattern the cron router uses with
``get_agent_for_request``.
"""

from __future__ import annotations

from typing import Awaitable, Callable, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .manager import RegistrationError
from .protocol import PROTOCOL_DOC


class RegisterBody(BaseModel):
    """Rule payload. Scripts are engine-managed: pass ``script_content``
    (inline, template-instantiated, or uploaded content) — it is written
    under the agent's ``event_trigger/scripts/`` and hash-pinned.
    ``agent_id`` comes from the URL path; the body field is accepted for
    backward compatibility but ignored."""

    name: str
    agent_id: str = ""                        # ignored — path wins
    interval_seconds: int = 60
    script_content: Optional[str] = None
    interpreter: Optional[str] = None
    action: str = "agent"                    # notify | agent
    prompt_template: str = "Event fired: [{title}] {event}\n(处理本事件前,请先通过 Skill 工具阅读 event-tasks 技能 / read the event-tasks skill first)"
    notify_template: str = "Event: [{title}] {event}"
    channel: str = "console"
    user_id: str = "default"
    session_id: Optional[str] = None
    cooldown_seconds: int = 0
    timeout_seconds: int = 120
    script_timeout_seconds: int = 60
    tool_safety: bool = False
    dispatch_mode: str = "stream"
    silent: bool = False
    save_result_to_inbox: bool = False
    max_triggers: int = 0
    config: Optional[dict] = None
    enabled: bool = False


def _rule_from_body(rule_id: Optional[str], body: RegisterBody, agent_id: str,
                    existing=None):
    from .models import (
        ActionKind,
        DispatchSpec,
        EventRule,
        PollSpec,
        RuntimeSpec,
        ScriptSpec,
    )

    script_path = existing.script.path if existing else ""
    kwargs: dict = dict(
        name=body.name,
        agent_id=agent_id,
        enabled=body.enabled,
        poll=PollSpec(interval_seconds=body.interval_seconds),
        script=ScriptSpec(path=script_path, interpreter=body.interpreter),
        action=ActionKind(body.action),
        prompt_template=body.prompt_template,
        notify_template=body.notify_template,
        dispatch=DispatchSpec(
            channel=body.channel,
            user_id=body.user_id,
            session_id=body.session_id,
        ),
        runtime=RuntimeSpec(
            timeout_seconds=body.timeout_seconds,
            script_timeout_seconds=body.script_timeout_seconds,
            cooldown_seconds=body.cooldown_seconds,
            tool_safety=body.tool_safety,
            dispatch_mode=body.dispatch_mode,
            silent=body.silent,
            save_result_to_inbox=body.save_result_to_inbox,
            max_triggers=body.max_triggers,
        ),
    )
    if rule_id:
        kwargs["id"] = rule_id
    elif existing:
        kwargs["id"] = existing.id  # omit otherwise -> default_factory generates
    return EventRule(**kwargs)


def build_router(
    resolve_bundle: Callable[[str], Awaitable[object]],
    injector=None,
) -> APIRouter:
    router = APIRouter(tags=["event-trigger"])  # mounted under /api/events

    async def _bundle(agent_id: str):
        try:
            return await resolve_bundle(agent_id)
        except KeyError as e:
            raise HTTPException(404, f"unknown agent: {agent_id}") from e

    # ---- global resources (agent-independent) ----

    @router.get("/templates")
    async def templates():
        from .templates import TEMPLATES
        return {"templates": TEMPLATES}

    @router.get("/protocol")
    async def protocol():
        return {"protocol": PROTOCOL_DOC}

    @router.get("/")
    async def root():
        """Index: agents with event-task data are discovered on demand."""
        agents = []
        if injector is not None:
            try:
                reg = injector._registry_()
                agents = sorted(reg.list_loaded_agents())
            except Exception:
                agents = []
        return {
            "service": "event-trigger",
            "version": "0.3",
            "usage": "GET/POST /api/events/{agent_id}/ ... — per-agent scope",
            "loaded_agents": agents,
        }

    # ---- agent-scoped ----

    @router.get("/{agent_id}/dispatch-targets")
    async def dispatch_targets(agent_id: str, channel: Optional[str] = None,
                               limit: int = 500):
        """Candidate dispatch targets derived from known chats (cron parity)."""
        bundle = await _bundle(agent_id)
        ws = bundle.workspace
        cm = getattr(ws, "chat_manager", None)
        if cm is None:
            return {"channels": ["console"], "items": []}

        chats = await cm.list_chats(channel=channel)
        deduped = {}
        for chat in chats:
            key = (chat.channel, chat.user_id, chat.session_id)
            if key not in deduped:
                deduped[key] = {
                    "channel": chat.channel,
                    "user_id": chat.user_id,
                    "session_id": chat.session_id,
                }
            if len(deduped) >= max(1, min(limit, 2000)):
                break
        items = list(deduped.values())
        channels = sorted({i["channel"] for i in items})
        if "console" not in channels:
            channels.insert(0, "console")
        return {"channels": channels, "items": items}

    @router.get("/{agent_id}/audit/recent")
    async def audit(agent_id: str, limit: int = 50):
        bundle = await _bundle(agent_id)
        return {"audit": await bundle.repo.recent_audit(limit=min(limit, 500))}

    @router.get("/{agent_id}/")
    async def list_rules(agent_id: str):
        bundle = await _bundle(agent_id)
        return {"rules": bundle.manager.describe()}

    @router.post("/{agent_id}/")
    async def register_rule(agent_id: str, body: RegisterBody,
                            validate_only: bool = False):
        if not body.script_content:
            raise HTTPException(400, "script_content required (all scripts are engine-managed)")
        bundle = await _bundle(agent_id)
        rule = _rule_from_body(None, body, agent_id)
        try:
            rule, warnings = await bundle.manager.register(
                rule, body.script_content, validate_only=validate_only
            )
        except RegistrationError as e:
            raise HTTPException(422, str(e)) from e
        return {"rule_id": rule.id, "warnings": warnings,
                "rules": bundle.manager.describe()}

    @router.put("/{agent_id}/{rule_id}")
    async def update_rule(agent_id: str, rule_id: str, body: RegisterBody):
        bundle = await _bundle(agent_id)
        existing = bundle.manager.events.get(rule_id)
        if not existing:
            raise HTTPException(404, f"unknown rule: {rule_id}")
        rule = _rule_from_body(rule_id, body, agent_id, existing)
        try:
            rule, warnings = await bundle.manager.update(
                rule, body.script_content, config=body.config)
        except RegistrationError as e:
            raise HTTPException(422, str(e)) from e
        return {"ok": True, "warnings": warnings}

    @router.delete("/{agent_id}/{rule_id}")
    async def delete_rule(agent_id: str, rule_id: str):
        bundle = await _bundle(agent_id)
        try:
            await bundle.manager.delete(rule_id)
        except RegistrationError as e:
            raise HTTPException(404, str(e)) from e
        return {"ok": True}

    @router.post("/{agent_id}/{rule_id}/enable")
    async def enable(agent_id: str, rule_id: str):
        # enable = register: re-validate (syntax + dry-run) and re-pin hash first
        bundle = await _bundle(agent_id)
        try:
            await bundle.manager.validate_for_enable(rule_id)
            await bundle.manager.set_enabled(rule_id, True)
        except RegistrationError as e:
            raise HTTPException(422, str(e)) from e
        return {"ok": True}

    @router.post("/{agent_id}/{rule_id}/disable")
    async def disable(agent_id: str, rule_id: str):
        bundle = await _bundle(agent_id)
        try:
            await bundle.manager.set_enabled(rule_id, False)
        except RegistrationError as e:
            raise HTTPException(404, str(e)) from e
        return {"ok": True}

    @router.post("/{agent_id}/{rule_id}/run")
    async def run_now(agent_id: str, rule_id: str):
        bundle = await _bundle(agent_id)
        try:
            return await bundle.manager.run_now(rule_id)
        except RegistrationError as e:
            raise HTTPException(404, str(e)) from e

    @router.get("/{agent_id}/{rule_id}/runs")
    async def runs(agent_id: str, rule_id: str, limit: int = 50):
        bundle = await _bundle(agent_id)
        return {"runs": await bundle.repo.recent_runs(rule_id,
                                                      limit=min(limit, 500))}

    return router
