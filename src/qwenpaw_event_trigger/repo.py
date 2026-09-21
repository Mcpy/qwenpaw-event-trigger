# -*- coding: utf-8 -*-
"""Persistence for the event-trigger registry.

- events.json : rules + states, atomic write (tmp + rename) — cron jobs.json counterpart
- runs.jsonl  : append-only run records
- audit.jsonl : append-only registry change log (who/when/what hash changed)
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Optional

from .models import AuditRecord, EventRule, EventsFile, RunRecord


class Repo:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.events_path = os.path.join(data_dir, "events.json")
        self.runs_path = os.path.join(data_dir, "runs.jsonl")
        self.audit_path = os.path.join(data_dir, "audit.jsonl")
        self._lock = asyncio.Lock()

    # ---- registry (events.json) ----

    def load(self) -> EventsFile:
        if not os.path.exists(self.events_path):
            return EventsFile()
        try:
            with open(self.events_path, "r", encoding="utf-8") as f:
                return EventsFile.model_validate(json.load(f))
        except Exception:
            # corrupted registry: keep a backup aside, start clean — never crash the host
            try:
                os.replace(self.events_path, self.events_path + ".corrupt")
            except OSError:
                pass
            return EventsFile()

    async def save(self, events: EventsFile) -> None:
        async with self._lock:
            await asyncio.to_thread(self._atomic_write, self.events_path, events.model_dump_json(indent=2))

    @staticmethod
    def _atomic_write(path: str, content: str) -> None:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)

    # ---- append-only logs ----

    async def append_run(self, rec: RunRecord) -> None:
        async with self._lock:
            await asyncio.to_thread(self._append_line, self.runs_path, rec.model_dump_json())

    async def append_audit(self, rec: AuditRecord) -> None:
        async with self._lock:
            await asyncio.to_thread(self._append_line, self.audit_path, rec.model_dump_json())

    @staticmethod
    def _append_line(path: str, line: str) -> None:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    # ---- convenience queries ----

    async def recent_runs(self, rule_id: Optional[str] = None, limit: int = 50) -> list[dict]:
        """Read the tail of runs.jsonl (newest last)."""
        if not os.path.exists(self.runs_path):
            return []
        rows: list[dict] = []

        def _read() -> None:
            with open(self.runs_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if rule_id and d.get("rule_id") != rule_id:
                        continue
                    rows.append(d)

        await asyncio.to_thread(_read)
        return rows[-limit:]

    async def recent_audit(self, limit: int = 50) -> list[dict]:
        if not os.path.exists(self.audit_path):
            return []
        rows: list[dict] = []

        def _read() -> None:
            with open(self.audit_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            rows.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue

        await asyncio.to_thread(_read)
        return rows[-limit:]
