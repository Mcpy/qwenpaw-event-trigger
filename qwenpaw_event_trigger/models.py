# -*- coding: utf-8 -*-
"""Data models for the event-trigger plugin.

Mirrors the design of QwenPaw's cron subsystem (app/crons/models.py):
ScheduleSpec(when) is replaced by PollSpec + a checker script; the
dispatch / runtime / record concepts are kept intentionally aligned.
"""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


def now_ts() -> float:
    return time.time()


def new_id() -> str:
    return uuid.uuid4().hex[:12]


class PollSpec(BaseModel):
    """How often the checker script runs. (cron's ScheduleSpec counterpart)"""

    interval_seconds: int = Field(default=60, ge=10)  # floor: resource guard


class ActionKind(str, Enum):
    notify = "notify"  # fire -> deliver text only, no agent reasoning
    agent = "agent"    # fire -> inject prompt into agent session


class DispatchSpec(BaseModel):
    """Where fired results go. Same shape philosophy as cron DispatchSpec."""

    channel: str = "console"
    user_id: str = "default"
    session_id: Optional[str] = None  # None -> dedicated per-rule session


class RuntimeSpec(BaseModel):
    timeout_seconds: int = Field(default=120, ge=1)       # agent reasoning timeout (cron parity)
    script_timeout_seconds: int = Field(default=60, ge=1)  # checker script timeout
    cooldown_seconds: int = Field(default=0, ge=0)         # suppress re-fire after a trigger
    max_triggers: int = Field(default=0, ge=0)             # 0 = unlimited; N = auto-disable after N fires
    tool_safety: bool = False            # True -> high-risk tools require approval (cron default: off)
    dispatch_mode: Literal["stream", "final"] = "stream"
    silent: bool = False                 # consume stream, no channel delivery (cron parity)
    save_result_to_inbox: bool = True    # write run result to inbox (cron default: on)


class ScriptSpec(BaseModel):
    path: str                                   # absolute path, registered only
    interpreter: Optional[str] = None           # default: platform python (sys.executable)
    content_hash: str = ""                      # SHA256 at registration; verified before every run


class EventRule(BaseModel):
    id: str = Field(default_factory=new_id)
    name: str
    enabled: bool = False   # cron parity: created disabled, user toggles on
    agent_id: str = "default"

    poll: PollSpec = Field(default_factory=PollSpec)
    script: ScriptSpec
    action: ActionKind = ActionKind.agent

    # agent action: prompt template; placeholders {title} {event} allowed
    prompt_template: str = "Event fired: [{title}] {event}\n(处理本事件前,请先通过 Skill 工具阅读 event-tasks 技能 / read the event-tasks skill first)"
    # notify action: message template; same placeholders
    notify_template: str = "Event: [{title}] {event}"

    dispatch: DispatchSpec = Field(default_factory=DispatchSpec)
    runtime: RuntimeSpec = Field(default_factory=RuntimeSpec)

    created_at: float = Field(default_factory=now_ts)
    updated_at: float = Field(default_factory=now_ts)


class RuleState(BaseModel):
    """Per-rule runtime state, persisted; fed back to scripts as EVENT_STATE."""

    state: Dict[str, Any] = {}            # script-owned hysteresis state
    last_run_at: Optional[float] = None
    last_triggered_at: Optional[float] = None   # cooldown reference
    last_error: Optional[str] = None
    run_count: int = 0
    trigger_count: int = 0


class AuditKind(str, Enum):
    register = "register"
    update = "update"
    enable = "enable"
    disable = "enable_off"
    delete = "delete"
    script_changed = "script_changed"


class AuditRecord(BaseModel):
    """Append-only registry change log (detection over prevention)."""

    ts: float = Field(default_factory=now_ts)
    kind: AuditKind
    rule_id: str
    name: str = ""
    detail: str = ""


class RunRecord(BaseModel):
    """One checker run / fire / error. Append-only (runs.jsonl)."""

    ts: float = Field(default_factory=now_ts)
    rule_id: str
    kind: Literal["check", "trigger", "error", "skipped"]
    ok: bool = True
    duration_ms: int = 0
    detail: str = ""


class EventsFile(BaseModel):
    """Single-file registry (cron's jobs.json counterpart)."""

    version: int = 1
    rules: list[EventRule] = Field(default_factory=list)
    states: Dict[str, RuleState] = Field(default_factory=dict)

    def get(self, rule_id: str) -> Optional[EventRule]:
        return next((r for r in self.rules if r.id == rule_id), None)
