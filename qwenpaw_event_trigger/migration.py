# -*- coding: utf-8 -*-
"""One-time migration: split the legacy global data dir into per-workspace dirs.

v0.2 stored everything under ``WORKING_DIR/event_trigger`` (single events.json
+ scripts/).  v0.3 aligns with cron: each agent's data lives in its own
``workspace_dir/event_trigger``.  This module moves rules, states and
engine-managed scripts there, per agent:

- Loaded agents are migrated eagerly at plugin startup.
- Agents whose workspace is not loaded yet are migrated lazily the first
  time their bundle is resolved (see plugin.get_bundle).
- The legacy file is kept as ``events.json.pre-migrate`` once every rule has
  been moved; runs/audit history stays in the legacy dir as an archive.
"""

from __future__ import annotations

import logging
import os
import shutil

from .models import RuleState
from .repo import Repo

logger = logging.getLogger("qwenpaw.event_trigger")

MIGRATED_SUFFIX = ".pre-migrate"


def legacy_exists(data_dir: str) -> bool:
    return os.path.isfile(os.path.join(data_dir, "events.json"))


def load_legacy_events(data_dir: str):
    """Return the legacy EventsFile (or None when absent / already migrated)."""
    if not legacy_exists(data_dir):
        return None
    try:
        return Repo(data_dir).load()
    except Exception:
        logger.warning("event-trigger: legacy events.json unreadable", exc_info=True)
        return None


def _copy_script(legacy_scripts_dir: str, target_scripts_dir: str,
                 rule_id: str, current_path: str) -> str:
    """Copy the engine-managed script of ``rule_id``; return the new path.

    External (path-referenced) scripts are left untouched.
    """
    legacy_scripts_dir = os.path.realpath(legacy_scripts_dir)
    if current_path and not os.path.realpath(current_path).startswith(
        legacy_scripts_dir + os.sep,
    ):
        return current_path  # referenced external script — not ours to move
    os.makedirs(target_scripts_dir, exist_ok=True)
    for fn in os.listdir(legacy_scripts_dir):
        if fn.startswith(f"{rule_id}_") and fn.endswith(".py"):
            src = os.path.join(legacy_scripts_dir, fn)
            dst = os.path.join(target_scripts_dir, fn)
            if os.path.realpath(src) != os.path.realpath(dst):
                shutil.copy2(src, dst)
            return dst
    return current_path


def migrate_agent(legacy_dir: str, agent_id: str, workspace_dir: str) -> int:
    """Move this agent's rules/states/scripts from the legacy dir into its
    workspace.  Idempotent: rules already present in the target are skipped.

    Returns the number of migrated rules.
    """
    legacy = load_legacy_events(legacy_dir)
    if legacy is None:
        return 0

    target_dir = os.path.join(workspace_dir, "event_trigger")
    target_repo = Repo(target_dir)
    target = target_repo.load()

    legacy_scripts_dir = os.path.join(legacy_dir, "scripts")
    target_scripts_dir = os.path.join(target_dir, "scripts")

    moved = 0
    for rule in list(legacy.rules):
        if (rule.agent_id or "default") != agent_id:
            continue
        if target.get(rule.id) is not None:
            continue  # already migrated — idempotent
        new_path = _copy_script(
            legacy_scripts_dir, target_scripts_dir, rule.id, rule.script.path or ""
        )
        rule.script.path = new_path
        target.rules.append(rule)
        target.states[rule.id] = legacy.states.get(rule.id) or RuleState()
        moved += 1

    if moved:
        target_repo.save(target)
        logger.info(
            "event-trigger: migrated %d rule(s) of agent '%s' -> %s",
            moved, agent_id, target_dir,
        )

    _finalize_legacy_if_empty(legacy_dir)
    return moved


def _finalize_legacy_if_empty(legacy_dir: str) -> None:
    """Rename the legacy events.json once no un-migrated rule is left."""
    legacy = load_legacy_events(legacy_dir)
    if legacy is None:
        return
    if legacy.rules:
        return  # some agent's workspace is not loaded yet — keep as source
    src = os.path.join(legacy_dir, "events.json")
    dst = src + MIGRATED_SUFFIX
    try:
        os.replace(src, dst)
        logger.info("event-trigger: legacy events.json archived as %s", dst)
    except OSError:
        logger.warning("event-trigger: could not archive legacy events.json",
                       exc_info=True)
