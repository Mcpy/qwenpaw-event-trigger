# -*- coding: utf-8 -*-
"""Smoke test: script_rel by-reference registration / rebind / traversal blocks."""
import asyncio, json, os, shutil, sys, tempfile

sys.path.insert(0, "/mnt/Projects/qwenpaw-event-trigger")
from qwenpaw_event_trigger.manager import RuleManager, RegistrationError
from qwenpaw_event_trigger.models import EventRule, EventsFile, ScriptSpec

PROBE = 'import json,os\nprint(json.dumps({"triggered": False, "state": {}}))\n'

class StubEngine:
    def __init__(self):
        self.events = EventsFile()
    async def upsert_rule(self, rule, *, audit_detail=""):
        self.events.rules = [r for r in self.events.rules if r.id != rule.id]
        self.events.rules.append(rule)

class StubRepo:
    async def save(self, events):
        pass

def make_rule(name):
    return EventRule(id=f"r_{name}", name=name, interval_seconds=60,
                     script=ScriptSpec(path=""))

async def main():
    tmp = tempfile.mkdtemp(prefix="etr_smoke_")
    m = RuleManager(StubEngine(), StubRepo(), tmp)
    ok = []
    def check(name, cond):
        ok.append((name, bool(cond)))
        print(("✓" if cond else "✗"), name)

    # seed two by-hand scripts (as if written via the platform file page)
    with open(os.path.join(m.scripts_dir, "ok_probe.py"), "w") as f:
        f.write(PROBE)
    with open(os.path.join(m.scripts_dir, "other.py"), "w") as f:
        f.write("# different probe\n" + PROBE)

    # 1. register by reference
    r1 = make_rule("byref")
    r1, w = await m.register(r1, script_rel="ok_probe.py")
    check("register by script_rel", os.path.basename(r1.script.path) == "ok_probe.py"
          and bool(r1.script.content_hash))

    # 2. file NOT rewritten by registration
    with open(os.path.join(m.scripts_dir, "ok_probe.py")) as f:
        check("by-ref file untouched", f.read() == PROBE)

    # 3. traversal / subdir / missing / extension / mutual-exclusion
    for rel, label in [("../evil.py", "traversal blocked"),
                       ("sub/x.py", "subdir blocked"),
                       ("nope.py", "missing blocked"),
                       ("ok_probe.txt", "non-py blocked")]:
        try:
            await m.register(make_rule("x"), script_rel=rel)
            check(label, False)
        except RegistrationError:
            check(label, True)

    # 4. inline wins error when both given
    try:
        await m.register(make_rule("x"), "print(1)", script_rel="ok_probe.py")
        check("mutual exclusion", False)
    except RegistrationError:
        check("mutual exclusion", True)

    # 5. PUT rebind to another file: content untouched, hash re-pinned
    old_hash = r1.script.content_hash
    r1b, _ = await m.update(r1, script_rel="other.py")
    check("rebind path", os.path.basename(r1b.script.path) == "other.py")
    check("rebind hash re-pinned", r1b.script.content_hash != old_hash)
    with open(os.path.join(m.scripts_dir, "other.py")) as f:
        check("rebound file untouched", f.read() == "# different probe\n" + PROBE)

    # 6. update WITHOUT script_rel/script_content: file untouched (regression)
    r1c, _ = await m.update(r1b, config=None)
    check("plain update keeps binding", os.path.basename(r1c.script.path) == "other.py")

    # 7. legacy inline path still works
    r2, _ = await m.register(make_rule("inline"), PROBE)
    check("inline still works", os.path.isfile(r2.script.path)
          and os.path.basename(r2.script.path).startswith("r_inline"))

    passed = sum(1 for _, c in ok if c)
    print(f"\n{passed}/{len(ok)} passed")
    shutil.rmtree(tmp, ignore_errors=True)
    sys.exit(0 if passed == len(ok) else 1)

asyncio.run(main())
