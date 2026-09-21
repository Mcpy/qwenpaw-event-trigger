---
name: event-tasks
description: Use ONLY for condition-triggered automation — when an external event occurs (price crosses a threshold, file modified, HTTP service down, port unreachable, keyword appears in logs) and you want to fire reasoning or a notification automatically. Managed via the /api/events/ REST API; checker scripts are polled at a fixed interval. For time-based schedules use the cron skill instead.
metadata:
  builtin_skill_version: "1.0"
  qwenpaw:
    emoji: "⚡"
---

# Event Task Management (condition-triggered)

Event task = **condition-driven** (fires only when something happens); cron = **time-driven** (fires when the clock says so).

## When to use

### Use event tasks when
- The user says "when/if X happens, do Y": NVDA crosses a price, a file changes, a service goes down, ERROR appears in logs
- The trigger cannot be expressed as a time, only as a polled condition
- You need event-storm protection (cooldown / hysteresis)

### Do NOT use event tasks when
- "Every day at 9am / hourly" → use **cron**
- It's a one-off to run right now → just do it, don't create a task
- The trigger condition is unclear → ask the user first

### Combining with cron
- cron suits periodic checkups (low-frequency, comprehensive); event tasks suit immediate response to anomalies
- Both can coexist for the same subject: cron daily digest + event task breakout alert

---

## Management API (HTTP)

Base: `http://127.0.0.1:8088` (no auth on localhost); remote needs `Authorization: Bearer <token>`.

```
GET    /api/events/                 list tasks (state/counters/errors)
POST   /api/events/                 create (runs the registration gate)
PUT    /api/events/{id}             update (script changes are re-validated)
DELETE /api/events/{id}             delete
POST   /api/events/{id}/enable      enable
POST   /api/events/{id}/disable     disable
POST   /api/events/{id}/run         one manual check now
GET    /api/events/{id}/runs        run history
GET    /api/events/protocol         full checker-script protocol
```

## Creating a task

`POST /api/events/` with JSON:

```json
{
  "name": "task name",
  "agent_id": "<your agent_id, matching Agent Identity in the system prompt>",
  "interval_seconds": 60,
  "script_content": "<full checker script (python)>",
  "action": "agent",
  "prompt_template": "Event fired: [{title}] {event}",
  "channel": "console",
  "user_id": "default",
  "session_id": null,
  "cooldown_seconds": 600,
  "enabled": false
}
```

- Use `"script_path": "/abs/path.py"` instead of `script_content` if the script already exists (prefer `script_content` — the engine manages the file)
- `action`: `notify` (deliver a message only, zero tokens) / `agent` (fire reasoning)
- `interval_seconds` minimum is 10
- `cooldown_seconds`: suppress re-fires after a trigger; the script's `cooldown` output field can override per-fire
- Leave `session_id` empty for a dedicated accumulating session (recommended)
- `enabled`: created disabled by default; enable afterwards via `POST /{id}/enable`

## Checker-script protocol (core)

**IN**: env `EVENT_STATE` (JSON of the last persisted state; `{}` on first run), `EVENT_RULE_ID`, `EVENT_RULE_NAME`.
**OUT**: print one JSON line to stdout:

```json
{"triggered": true, "title": "title", "event": "body passed to agent/notification", "state": {"armed": false}}
```

- `triggered` must be boolean; `state` is persisted by the engine and fed back via `EVENT_STATE` next run
- Non-zero exit = script error (logged, never fires)
- stdout larger than 64KB is rejected

### Hysteresis (anti-refire) canonical pattern

Keep an "armed" flag in `state`: fire only when armed and the condition holds → set `armed:false`; re-arm silently when the release condition holds. Template:

```python
#!/usr/bin/env python3
import json, os
st = json.loads(os.environ.get("EVENT_STATE") or "{}")
armed = bool(st.get("armed", True))
# ... check logic producing should_fire ...
if armed and should_fire:
    print(json.dumps({"triggered": True, "title": "...", "event": "...", "state": {"armed": False}}, ensure_ascii=False))
else:
    print(json.dumps({"triggered": False, "state": {"armed": armed or reset_condition}}, ensure_ascii=False))
```

## Script authoring guide

### Format spec

| Item | Spec |
| --- | --- |
| Language | Python first (runs with the platform venv python; platform libs importable); any interpreter via the `interpreter` field |
| Input | env `EVENT_STATE` (JSON of last state, `{}` first run), `EVENT_RULE_ID`, `EVENT_RULE_NAME` |
| Output | one JSON line on stdout: boolean `triggered` required; optional `title` / `event` / `cooldown` (seconds, overrides rule default) / `state` (persisted and fed back) |
| Exit code | 0 = ok (JSON is read); non-zero = script error (logged, never fires) |
| Limits | stdout ≤ 64KB; timeout 60s default (`script_timeout_seconds`); interval ≥ 10s |
| event field | for notify tasks it IS the notification body; for agent tasks it fills the `{event}` placeholder in the prompt |

### Universal skeleton (hysteresis, copy-ready)

```python
#!/usr/bin/env python3
import json, os

st = json.loads(os.environ.get("EVENT_STATE") or "{}")
armed = bool(st.get("armed", True))

# --- your check logic produces two booleans ---
should_fire = False      # trigger condition met?
reset_condition = False  # release (re-arm) condition met?

out = {"triggered": False, "state": dict(st)}
if armed and should_fire:
    out.update({
        "triggered": True,
        "title": "short title",
        "event": "Detailed body: what happened, key numbers. Fed to the agent as reasoning input.",
        "state": {"armed": False},
    })
elif reset_condition:
    out["state"] = {"armed": True}
print(json.dumps(out, ensure_ascii=False))
```

### Authoring rules

1. **Persistent conditions need hysteresis**: without an armed gate, a continuously-true condition fires every interval (storm). Fire → `armed:false`; re-arm only on release
2. **One-shot flags must NOT live in state**: the registration dry-run actually executes the script once and persists state, consuming the latch; put one-shot detection in the **event source itself** (e.g. does the file exist yet)
3. **stdout discipline**: debug prints must not start with `{`; the engine reads the last parseable JSON line
4. **Do not touch engine internals**: scripts interact only via `EVENT_STATE` (in) and stdout (out)
5. **Set timeouts on external requests**: the script has a total timeout; inner network calls need shorter ones

### Bundled templates

`GET /api/events/templates` returns 5 built-in templates (stock-threshold hysteresis / HTTP probe / file change / port alive / log keyword), each with `params` and the full `script`. Flow: fetch → substitute `__PLACEHOLDERS__` → POST as `script_content`. The console "from template" tab uses the same source.

## Minimum info before creating

Ask the user first if any of these are missing:
- Trigger condition (what the checker tests) and check interval
- `action` (notify vs agent reasoning)
- Delivery target channel / user_id
- Cooldown (mandatory when the event can fire repeatedly)

## Common mistakes

1. **One-shot flag in state**: consumed by the registration dry-run → detect one-shot-ness from the event source, not script state
2. **Non-JSON debug output on stdout**: engine takes the last `{`-leading parseable line; keep debug lines clear of it
3. **No cooldown with a persistent condition**: fires every interval = storm; use hysteresis or cooldown
4. **Editing the script without re-PUT**: hash check refuses to run; the rule shows last_error
5. **Wrong/missing agent_id**: the task lands on another agent's workspace; must match the current Agent Identity

## Minimal workflow

```
1. Condition-triggered (event task) or time-triggered (cron)?
2. Confirm the trigger condition with the user → design the checker (with hysteresis)
3. POST /api/events/ create (inline script_content, enabled=false)
4. POST /{id}/run to verify one check behaves as expected
5. POST /{id}/enable
6. Inspect via GET /{id}/runs; modify via PUT
```
