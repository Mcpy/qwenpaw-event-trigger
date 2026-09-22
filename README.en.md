# ⚡ QwenPaw Event Trigger (事件任务)

[中文](./README.md) | English

**The condition-driven twin of QwenPaw's cron jobs.**

> Cron answers "*when* to do it"; Event Tasks answer "*when something happens*, do it."

QwenPaw's automation was time-only (cron / heartbeat). Conditions like "analyze when NVDA crosses 250", "notify me the moment the service dies", "investigate when ERROR appears in logs" previously required gluing external scripts to notification channels. This plugin turns **poll → condition → action** into a first-class capability, on par with cron.

Built against a real gap: [#338 (webhook support, open since 2026-03)](https://github.com/agentscope-ai/QwenPaw/issues/338) and [#7657 (ntfy channel)](https://github.com/agentscope-ai/QwenPaw/issues/7657) — no ecosystem solution exists yet.

## Highlights

- 🔁 **Two entry points**: console UI (sidebar "Event Tasks") + agent-authored tasks via the bilingual `event-tasks` skill
- 🗂 **Per-agent isolation (v0.3, cron-aligned)**: rules/scripts/runs live in each agent's workspace (`workspace_dir/event_trigger/`), served under `/api/events/{agent_id}/` — no cross-visibility, no cross-interference
- 🧩 **Bundled agent skill, self-teaching**: the `event-tasks` skill (bilingual) is injected on install — it is the manual written *for agents* (protocol, templates, param evolution, common pitfalls). An agent that reads it can author scripts and manage tasks on its own; humans don't need the docs.
- 🛡 **Enable = register**: creation validates only; **enabling** runs syntax check → dry-run (executes once for real, resets state) → hash pinning. Disable = deregister; editing a script while running is refused (disable → enable to recover)
- ⚙️ **In-script CONFIG params**: declare a `CONFIG = {...}` literal at the top of the script (parsed via ast, never executed) — the UI auto-generates a parameter form; changing params = re-register, config and code live in one self-contained file
- 🔢 **max_triggers**: auto-disable after N fires (0 = unlimited); the per-round counter resets on enable — a fire-once sentinel
- 🌊 **Anti-storm**: rule-level cooldown + script-level hysteresis (state persisted by the engine and fed back)
- 🎯 **Two actions**: `notify` (zero tokens) / `agent` (**in-process injection** via `stream_query` — same path as cron, no HTTP/SSE overhead)
- 📡 **Dispatch modes**: `stream` (per-event forwarding) / `final`; silent delivery supported
- 🌍 **Bilingual**: UI / agent skill / template metadata (zh/en)
- 📦 **5 bundled templates**: stock dual-bound monitor (NVDA via Yahoo, up/down hysteresis) / HTTP probe / file change / port alive / log keyword
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

## Fire-evolve loop (core pattern)

```text
rule (UP=100, DOWN=90, max_triggers=1) -> price crosses 100 -> fire + auto-disable
  -> agent reasons "watch 105-120" -> PUT new CONFIG + enable (counter resets)
  -> next round: cross 120 or fall back to 105 -> fire again -> evolve again
```

Three decision layers: the **script owns the intelligence** (hysteresis, release rules), the **config owns the bounds** (max_triggers/timeouts/cooldown), the **engine owns the bookkeeping** (state storage, resets, scheduling) — it never interprets the script's state semantics.

## Security model

Scripts run inside your local trust domain (equivalent to writing your own crontab) — no sandbox theater. What the engine prevents: **unregistered scripts running** (registry-only), **silent tampering** (SHA-256 lock + audit log), and **resource abuse** (timeout / output cap / interval floor). Community templates: read the source before use; market-listed ones go through platform scanning.

## Roadmap

- List on the official plugin market
- CLI client (standalone `qwenpaw-event` pip package wrapping the REST API — the plugin system has no CLI extension point; cron's CLI is a built-in kernel subcommand)
- Execution model selection (cron parity) · Webhook-type event sources

## FAQ

**Q: Who maintains the `armed` state?**
The script defines its semantics; the engine stores it, feeds it back via `EVENT_STATE`, and resets it on re-registration (create/save/enable = a fresh round).

**Q: Does deleting a task delete the script?**
Yes — the engine-managed script is removed with the task (the confirm dialog warns you); a startup GC sweeps orphans. Path-referenced external scripts are untouched.

## License

[Apache 2.0](./LICENSE)
