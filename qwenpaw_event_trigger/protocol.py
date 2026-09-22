# -*- coding: utf-8 -*-
"""Checker script protocol: invocation, parsing, validation, integrity.

Contract (language-agnostic):
  IN : env EVENT_STATE (JSON, previous persisted state; "{}" on first run)
       env EVENT_RULE_ID, EVENT_RULE_NAME
  OUT: stdout must contain a JSON object (last parseable '{' line wins):
       {
         "triggered": bool,                 # required
         "title": str,                      # optional
         "event": str,                      # optional, human-readable summary
         "cooldown": int,                   # optional seconds, overrides rule default
         "state": {...}                     # optional, persisted & fed back next run
       }
  Exit code: 0 = ran (read JSON), non-zero = script error (logged, never fires).

Integrity: registration records SHA256 of the file; every run re-verifies —
a modified script is refused until re-registered (re-validated).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from typing import Any, Dict, Optional, Tuple

MAX_STDOUT_BYTES = 64 * 1024  # flood guard

PROTOCOL_DOC = """\
Event checker script protocol
=============================
IN : env EVENT_STATE   - JSON string of the previous persisted state ("{}" on first run)
       EVENT_RULE_ID / EVENT_RULE_NAME
OUT: stdout must contain a JSON object:
       {"triggered": bool, "title": str?, "event": str?, "cooldown": int?, "state": {...}?}
     "state" is persisted by the engine and passed back as EVENT_STATE next run
     (use it for hysteresis / arming logic).
Exit 0 = ok; non-zero = error (logged, never fires).
"""


class ProtocolError(Exception):
    pass


def compute_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve_command(path: str, interpreter: Optional[str]) -> list[str]:
    """Build argv. Default: platform python for .py (inherits QwenPaw's venv),
    shebang-direct otherwise."""
    if interpreter:
        return interpreter.split() + [path]
    if path.endswith(".py"):
        return [sys.executable, path]
    return [path]


def parse_output(stdout: str) -> Dict[str, Any]:
    """Last parseable JSON-object line wins (debug prints tolerated)."""
    obj: Optional[Dict[str, Any]] = None
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                cand = json.loads(line)
                if isinstance(cand, dict):
                    obj = cand
            except json.JSONDecodeError:
                continue
    if obj is None:
        raise ProtocolError("no JSON object found on stdout (protocol violation)")
    if not isinstance(obj.get("triggered"), bool):
        raise ProtocolError('output JSON must contain boolean field "triggered"')
    return obj


def run_script(
    path: str,
    state: Dict[str, Any],
    rule_id: str,
    rule_name: str,
    interpreter: Optional[str],
    timeout_seconds: int,
    expected_hash: str,
) -> Tuple[Dict[str, Any], int]:
    """Blocking run of one check. Raises ProtocolError / subprocess exceptions.

    Returns (parsed_output, duration_ms).
    """
    if not os.path.isfile(path):
        raise ProtocolError(f"script not found: {path}")
    if expected_hash:
        actual = compute_hash(path)
        if actual != expected_hash:
            raise ProtocolError(
                f"script content changed since registration "
                f"(expected {expected_hash[:12]}..., got {actual[:12]}...); "
                f"re-register to re-validate"
            )

    env = dict(os.environ)
    env["EVENT_STATE"] = json.dumps(state, ensure_ascii=False)
    env["EVENT_RULE_ID"] = rule_id
    env["EVENT_RULE_NAME"] = rule_name

    proc = subprocess.run(
        resolve_command(path, interpreter),
        env=env,
        capture_output=True,
        timeout=timeout_seconds,
        stdin=subprocess.DEVNULL,
    )
    if proc.returncode != 0:
        stderr_tail = proc.stderr.decode(errors="replace")[-500:]
        raise ProtocolError(f"script exited {proc.returncode}: {stderr_tail}")

    stdout = proc.stdout.decode(errors="replace")
    if len(proc.stdout) > MAX_STDOUT_BYTES:
        raise ProtocolError(f"stdout exceeds {MAX_STDOUT_BYTES} bytes (flood guard)")
    return parse_output(stdout), 0


def validate_python_syntax(path: str) -> None:
    """py_compile gate for .py scripts (part of registration)."""
    if not path.endswith(".py"):
        return
    import py_compile

    py_compile.compile(path, doraise=True)


# ---- CONFIG block (script-declared parameters) ----
# A top-level `CONFIG = {...}` literal dict declares user-tunable parameters.
# Parsed with ast.literal_eval (never executed); rewritten in place when the
# user edits parameters. Hash pinning covers the WHOLE file — editing params
# therefore means disable -> enable (or save), which re-registers by design.

CONFIG_VAR = "CONFIG"


def parse_config(source: str) -> Tuple[Dict[str, Any], Optional[Tuple[int, int]]]:
    """Extract the top-level CONFIG literal dict from script source.

    Returns (config, span) where span = (start_line, end_line), 0-based,
    end-exclusive — usable as a line slice for in-place rewriting.
    Returns ({}, None) when the script declares no CONFIG.
    Raises ProtocolError when CONFIG exists but is not a literal dict.
    """
    import ast

    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
            if any(isinstance(t, ast.Name) and t.id == CONFIG_VAR for t in node.targets):
                try:
                    cfg = ast.literal_eval(node.value)
                except Exception as e:
                    raise ProtocolError(f"CONFIG must be a literal dict: {e}") from e
                if not isinstance(cfg, dict):
                    raise ProtocolError("CONFIG must be a dict")
                return cfg, (node.lineno - 1, node.end_lineno)
    return {}, None


def rewrite_config(source: str, new_cfg: Dict[str, Any]) -> str:
    """Rewrite the CONFIG assignment block, preserving every other line."""
    _, span = parse_config(source)
    if span is None:
        raise ProtocolError("script has no CONFIG block to update")
    start, end = span
    lines = source.splitlines(keepends=True)
    rendered = "CONFIG = " + json.dumps(new_cfg, ensure_ascii=False, indent=4) + "\n"
    return "".join(lines[:start]) + rendered + "".join(lines[end:])


def parse_config_file(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        cfg, _ = parse_config(f.read())
    return cfg
