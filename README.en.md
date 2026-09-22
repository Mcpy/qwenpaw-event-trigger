# ⚡ QwenPaw Event Trigger (事件任务)

[中文](./README.md) | English

**The condition-driven twin of QwenPaw's cron jobs.**

> Cron answers "*when* to do it"; Event Tasks answer "*when something happens*, do it."

QwenPaw's automation was time-only (cron / heartbeat). Conditions like "analyze when NVDA crosses 250", "notify me the moment the service dies", "investigate when ERROR appears in logs" previously required gluing external scripts to notification channels. This plugin turns **poll → condition → action** into a first-class capability, on par with cron.

Built against a real gap: [#338 (webhook support, open since 2026-03)](https://github.com/agentscope-ai/QwenPaw/issues/338) and [#7657 (ntfy channel)](https://github.com/agentscope-ai/QwenPaw/issues/7657) — no ecosystem solution exists yet.

## Highlights

- 🔁 **Two entry points**: console UI (sidebar "Event Tasks") + agent-authored tasks via the bilingual `event-tasks` skill
- 🛡 **Registration gate**: syntax check → dry-run (executes once for real, seeds state) → content-hash pinning. No script runs without registration; edited scripts are refused until re-validated
- 🌊 **Anti-storm**: rule-level cooldown + script-level hysteresis (state persisted by the engine and fed back)
- 🎯 **Two actions**: `notify` (zero tokens) / `agent` (**in-process injection** via `stream_query` — same path as cron, no HTTP/SSE overhead)
- 📡 **Dispatch modes**: `stream` (per-event forwarding) / `final`; silent delivery supported
- 🌍 **Bilingual**: UI / agent skill / template metadata (zh/en)
- 📦 **5 bundled templates**: stock threshold (NVDA via Yahoo) / HTTP probe / file change / port alive / log keyword
- 🔒 **Security**: registration registry (no folder scanning) + SHA-256 integrity lock + resource guards (timeout / 64KB stdout cap / interval floor) + audit log

## Install

```bash
qwenpaw plugin install /path/to/qwenpaw-event-trigger
```

- Sidebar gains "⚡ Event Tasks"; the `event-tasks` skill is auto-installed into workspaces (zh/en)
- Data lives in `~/.qwenpaw/event_trigger/` (survives uninstall)

## Quick start

**Console**: sidebar → Event Tasks → + Create Task → checker "From template" (stock threshold, NVDA/200 default) → Agent action → pick channel/user/session from dropdowns → Save (auto-validated) → enable.

**Agent**: *"Watch NVDA and analyze + notify me when it crosses 250."* The agent designs a hysteresis checker, registers it via `POST /api/events/`, verifies with `run`, then enables it.

## Checker protocol

```text
IN : env EVENT_STATE (last persisted state, "{}" first run), EVENT_RULE_ID, EVENT_RULE_NAME
OUT: one JSON line on stdout:
     {"triggered": bool, "title": str?, "event": str?, "cooldown": int?, "state": {...}?}
Exit 0 = ok; non-zero = error (logged, never fires). stdout ≤ 64KB. Timeout 60s default.
```

Hysteresis skeleton and the full spec: `GET /api/events/protocol`; ready-made templates: `GET /api/events/templates`.

## Security model

Scripts run inside your local trust domain (equivalent to writing your own crontab) — no sandbox theater. What the engine prevents: **unregistered scripts running** (registry-only), **silent tampering** (SHA-256 lock + audit log), and **resource abuse** (timeout / output cap / interval floor). Community templates: read the source before use; market-listed ones go through platform scanning.

## Roadmap

- List on the official plugin market
- CLI client (standalone `qwenpaw-event` pip package wrapping the REST API — the plugin system has no CLI extension point; cron's CLI is a built-in kernel subcommand)
- Execution model selection (cron parity) · Webhook-type event sources

## License

[MIT](./LICENSE)
