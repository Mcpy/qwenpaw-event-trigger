# -*- coding: utf-8 -*-
"""REST API under /api/events (FastAPI APIRouter, mounted by the plugin)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .manager import RegistrationError, RuleManager
from .protocol import PROTOCOL_DOC
from .repo import Repo


class RegisterBody(BaseModel):
    """Rule payload. Either give an absolute script path, or inline content
    (preferred for agent-authored rules — server writes it under its
    controlled scripts dir)."""

    name: str
    agent_id: str = "default"
    interval_seconds: int = 60
    script_path: Optional[str] = None
    script_content: Optional[str] = None
    interpreter: Optional[str] = None
    action: str = "agent"                    # notify | agent
    prompt_template: str = "Event fired: [{title}] {event}"
    notify_template: str = "Event: [{title}] {event}"
    channel: str = "console"
    user_id: str = "default"
    session_id: Optional[str] = None
    cooldown_seconds: int = 0
    timeout_seconds: int = 120
    script_timeout_seconds: int = 60
    share_session: bool = False
    tool_safety: bool = True
    dispatch_mode: str = "final"
    silent: bool = False
    enabled: bool = True


def _rule_from_body(rule_id: Optional[str], body: RegisterBody, existing=None):
    from .models import (
        ActionKind,
        DispatchSpec,
        EventRule,
        PollSpec,
        RuntimeSpec,
        ScriptSpec,
    )

    script_path = body.script_path or (existing.script.path if existing else "")
    kwargs: dict = dict(
        name=body.name,
        agent_id=body.agent_id,
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
            share_session=body.share_session,
            tool_safety=body.tool_safety,
            dispatch_mode=body.dispatch_mode,
            silent=body.silent,
        ),
    )
    if rule_id:
        kwargs["id"] = rule_id
    elif existing:
        kwargs["id"] = existing.id  # omit otherwise -> default_factory generates
    return EventRule(**kwargs)


def build_router(manager: RuleManager, repo: Repo) -> APIRouter:
    router = APIRouter(tags=["event-trigger"])  # mounted under /api/events via register_http_router

    @router.get("/protocol")
    async def protocol():
        return {"protocol": PROTOCOL_DOC}

    @router.get("/audit/recent")
    async def audit(limit: int = 50):
        return {"audit": await repo.recent_audit(limit=min(limit, 500))}

    @router.get("/")
    async def list_rules():
        return {"rules": manager.describe()}

    @router.post("/")
    async def register_rule(body: RegisterBody, validate_only: bool = False):
        if not body.script_path and not body.script_content:
            raise HTTPException(400, "script_path or script_content required")
        rule = _rule_from_body(None, body)
        try:
            rule, warnings = await manager.register(
                rule, body.script_content, validate_only=validate_only
            )
        except RegistrationError as e:
            raise HTTPException(422, str(e)) from e
        return {"rule_id": rule.id, "warnings": warnings, "rules": manager.describe()}

    @router.put("/{rule_id}")
    async def update_rule(rule_id: str, body: RegisterBody):
        existing = manager.events.get(rule_id)
        if not existing:
            raise HTTPException(404, f"unknown rule: {rule_id}")
        rule = _rule_from_body(rule_id, body, existing)
        try:
            rule, warnings = await manager.update(rule, body.script_content)
        except RegistrationError as e:
            raise HTTPException(422, str(e)) from e
        return {"ok": True, "warnings": warnings}

    @router.delete("/{rule_id}")
    async def delete_rule(rule_id: str):
        try:
            await manager.delete(rule_id)
        except RegistrationError as e:
            raise HTTPException(404, str(e)) from e
        return {"ok": True}

    @router.post("/{rule_id}/enable")
    async def enable(rule_id: str):
        try:
            await manager.set_enabled(rule_id, True)
        except RegistrationError as e:
            raise HTTPException(404, str(e)) from e
        return {"ok": True}

    @router.post("/{rule_id}/disable")
    async def disable(rule_id: str):
        try:
            await manager.set_enabled(rule_id, False)
        except RegistrationError as e:
            raise HTTPException(404, str(e)) from e
        return {"ok": True}

    @router.post("/{rule_id}/run")
    async def run_now(rule_id: str):
        try:
            return await manager.run_now(rule_id)
        except RegistrationError as e:
            raise HTTPException(404, str(e)) from e

    @router.get("/{rule_id}/runs")
    async def runs(rule_id: str, limit: int = 50):
        return {"runs": await repo.recent_runs(rule_id, limit=min(limit, 500))}

    return router
