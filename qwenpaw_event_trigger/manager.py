# -*- coding: utf-8 -*-
"""Rule management: the registration gate.

Every script — handwritten, agent-authored, or template-instantiated —
enters through the same gate: syntax check -> protocol dry-run (which also
initializes persisted state) -> hash pinning -> registry upsert.
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from .engine import Engine
from .models import EventRule, EventsFile, RuleState
from .protocol import (
    ProtocolError,
    compute_hash,
    rewrite_config,
    run_script,
    validate_python_syntax,
)


class RegistrationError(Exception):
    pass


def _safe_name(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_")
    return s or "rule"


class RuleManager:
    def __init__(self, engine: Engine, repo, data_dir: str):
        self._engine = engine
        self._repo = repo
        self._data_dir = data_dir
        self.scripts_dir = os.path.join(data_dir, "scripts")
        os.makedirs(self.scripts_dir, exist_ok=True)

    @property
    def events(self) -> EventsFile:
        return self._engine.events

    # ---- registration gate ----

    async def register(
        self,
        rule: EventRule,
        script_content: Optional[str] = None,
        *,
        validate_only: bool = False,
    ) -> Tuple[EventRule, List[str]]:
        """Validate (and optionally persist) a rule. Returns (rule, warnings)."""
        warnings: List[str] = []

        if script_content is not None:
            fname = f"{rule.id}_{_safe_name(rule.name)}.py"
            rule.script.path = os.path.join(self.scripts_dir, fname)
            with open(rule.script.path, "w", encoding="utf-8") as f:
                f.write(script_content)

        path = rule.script.path
        if not path or not os.path.isfile(path):
            # v0.3.2: script_path mode retired — all scripts are engine-managed
            raise RegistrationError(
                "script_content required: all scripts are engine-managed "
                "under event_trigger/scripts/"
            )
        if not os.path.isabs(path):
            raise RegistrationError("script path must be absolute")

        # 1. syntax gate (python)
        try:
            await asyncio.to_thread(validate_python_syntax, path)
        except Exception as e:
            raise RegistrationError(f"syntax check failed: {e}") from e

        # 2. protocol dry-run — also initializes persisted state
        try:
            out, _ = await asyncio.to_thread(
                run_script,
                path, {}, rule.id, rule.name,
                rule.script.interpreter,
                rule.runtime.script_timeout_seconds,
                "",  # no hash check yet (file just written / first validation)
            )
        except ProtocolError as e:
            raise RegistrationError(f"dry-run failed: {e}") from e
        except Exception as e:
            raise RegistrationError(f"dry-run crashed: {e!r}") from e
        if not isinstance(out.get("state"), dict):
            warnings.append("dry-run returned no 'state'; starting with {}")

        # 3. hash pinning
        rule.script.content_hash = await asyncio.to_thread(compute_hash, path)

        # 4. registry upsert (audit + task spawn handled by engine)
        if not validate_only:
            await self._engine.upsert_rule(
                rule, audit_detail=f"hash={rule.script.content_hash[:12]}"
            )
            # (re-)registration starts a FRESH monitoring round:
            # state resets; the dry-run result is validation-only and is discarded
            self._engine.events.states[rule.id] = RuleState()  # force reset
            await self._repo.save(self._engine.events)
        else:
            warnings.append("validate-only: nothing persisted")
        return rule, warnings

    async def update(
        self, rule: EventRule, script_content: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> Tuple[EventRule, List[str]]:
        old = self._engine.events.get(rule.id)
        if not old:
            raise RegistrationError(f"unknown rule: {rule.id}")
        rule.created_at = old.created_at
        if config is not None:
            path = rule.script.path or old.script.path
            rule.script.path = path
            if not os.path.isfile(path):
                raise RegistrationError(f"script not found: {path}")
            with open(path, "r", encoding="utf-8") as f:
                source = f.read()
            try:
                new_source = rewrite_config(source, config)
            except ProtocolError as e:
                raise RegistrationError(str(e)) from e
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_source)
        return await self.register(rule, script_content)

    async def validate_for_enable(self, rule_id: str) -> EventRule:
        """enable = register: re-validate (syntax + dry-run seeding state) and
        re-pin the hash. Raises RegistrationError -> caller refuses to enable."""
        rule = self._engine.events.get(rule_id)
        if not rule:
            raise RegistrationError(f"unknown rule: {rule_id}")
        path = rule.script.path
        if not path or not os.path.isfile(path):
            raise RegistrationError(f"script not found: {path}")
        try:
            await asyncio.to_thread(validate_python_syntax, path)
            out, _ = await asyncio.to_thread(
                run_script, path, {}, rule.id, rule.name,
                rule.script.interpreter, rule.runtime.script_timeout_seconds, "",
            )
        except ProtocolError as e:
            raise RegistrationError(f"启用校验失败: {e}") from e
        except Exception as e:
            raise RegistrationError(f"启用校验崩溃: {e!r}") from e
        rule.script.content_hash = await asyncio.to_thread(compute_hash, path)
        # (re-)enable starts a FRESH monitoring round: state resets, so a
        # condition that is ALREADY true at enable time fires on the first
        # real check (monitoring-system convention), instead of being
        # silently consumed by the validation dry-run.
        self._engine.events.states[rule_id] = RuleState()  # force reset
        await self._repo.save(self._engine.events)
        return rule

    async def set_enabled(self, rule_id: str, enabled: bool) -> EventRule:
        rule = await self._engine.set_enabled(rule_id, enabled)
        if rule is None:
            raise RegistrationError(f"unknown rule: {rule_id}")
        return rule

    async def delete(self, rule_id: str) -> EventRule:
        rule = await self._engine.delete_rule(rule_id)
        if rule is None:
            raise RegistrationError(f"unknown rule: {rule_id}")
        # remove the engine-managed script file (only if inside scripts_dir
        # and no other rule references the same path)
        try:
            path = os.path.realpath(rule.script.path or "")
            root = os.path.realpath(self.scripts_dir)
            if path.startswith(root + os.sep):
                still_used = any(
                    os.path.realpath(r.script.path or "") == path
                    for r in self._engine.events.rules
                )
                if not still_used and os.path.isfile(path):
                    await asyncio.to_thread(os.remove, path)
        except OSError:
            pass
        return rule

    def gc_orphan_scripts(self) -> int:
        """Startup GC: remove files in scripts_dir not referenced by any rule."""
        referenced = {
            os.path.realpath(r.script.path or "")
            for r in self._engine.events.rules
        }
        removed = 0
        root = os.path.realpath(self.scripts_dir)
        for fn in os.listdir(self.scripts_dir):
            fp = os.path.realpath(os.path.join(self.scripts_dir, fn))
            if fp.startswith(root + os.sep) and fp not in referenced:
                try:
                    os.remove(fp)
                    removed += 1
                except OSError:
                    pass
        return removed

    async def run_now(self, rule_id: str) -> Dict[str, Any]:
        """Manual one-shot check (cron's 'run immediately' counterpart)."""
        rule = self._engine.events.get(rule_id)
        if not rule:
            raise RegistrationError(f"unknown rule: {rule_id}")
        started = time.time()
        await self._engine._check_once(rule)  # noqa: SLF001 — same subsystem
        return {"ok": True, "duration_ms": int((time.time() - started) * 1000)}

    def _safe_config(self, rule: EventRule) -> Dict[str, Any]:
        """Parsed CONFIG dict of the current script ({} when absent/unparseable)."""
        try:
            with open(rule.script.path, "r", encoding="utf-8") as f:
                from .protocol import parse_config
                cfg, _ = parse_config(f.read())
            return cfg
        except Exception:
            return {}

    def describe(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for r in self._engine.events.rules:
            st: RuleState = self._engine.events.states.get(r.id, RuleState())
            path = r.script.path or ""
            managed = bool(path) and os.path.realpath(path).startswith(
                os.path.realpath(self._data_dir) + os.sep
            )
            try:
                rel = os.path.relpath(path, os.path.dirname(self._data_dir)) if managed else None
            except ValueError:
                rel = None
            out.append(
                {
                    "id": r.id,
                    "name": r.name,
                    "enabled": r.enabled,
                    "agent_id": r.agent_id,
                    "interval_seconds": r.poll.interval_seconds,
                    "action": r.action.value,
                    "script": path,
                    "script_rel": rel,
                    "managed": managed,
                    "script_hash": r.script.content_hash[:12],
                    "dispatch": r.dispatch.model_dump(),
                    "runtime": r.runtime.model_dump(),
                    "cooldown_seconds": r.runtime.cooldown_seconds,
                    "config": self._safe_config(r),
                    "prompt_template": r.prompt_template,
                    "notify_template": r.notify_template,
                    "run_count": st.run_count,
                    "trigger_count": st.trigger_count,
                    "last_run_at": st.last_run_at,
                    "last_triggered_at": st.last_triggered_at,
                    "last_error": st.last_error,
                    "state": st.state,
                }
            )
        return out
