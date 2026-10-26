# -*- coding: utf-8 -*-
"""Regression tests for issue #1 (BeiMu-new):
1. checker stdio forced to UTF-8 (non-ASCII output survives on GBK hosts)
2. notify passes session_id through empty instead of fabricating event:<rule_id>
"""
import asyncio, os, sys, tempfile

sys.path.insert(0, "/mnt/Projects/qwenpaw-event-trigger")
from qwenpaw_event_trigger.protocol import run_script
from qwenpaw_event_trigger.models import DispatchSpec, EventRule, ScriptSpec
from qwenpaw_event_trigger.engine import Engine
from qwenpaw_event_trigger.models import EventsFile

class StubRepo:
    def load(self):
        return EventsFile()
    async def save(self, events):
        pass

ok = []
def check(name, cond):
    ok.append((name, bool(cond)))
    print(("✓" if cond else "✗"), name)

ENC_PROBE = (
    'import json,os\n'
    'print(json.dumps({"triggered": False, "state": {"enc": os.environ.get("PYTHONIOENCODING"), '
    '"utf8mode": os.environ.get("PYTHONUTF8")}}))\n'
)
CJK_PROBE = (
    'import json\n'
    'print(json.dumps({"triggered": True, "title": "中文标题·测试", '
    '"event": "中文正文 ¥ 不乱码"}, ensure_ascii=False))\n'
)

class StubCM:
    def __init__(self):
        self.calls = []
    async def send_text(self, **kw):
        self.calls.append(kw)

class StubInjector:
    def __init__(self, cm):
        self._cm = cm
    def channel_manager_for(self, agent_id):
        return self._cm

def main():
    tmp = tempfile.mkdtemp(prefix="etr_i1_")

    # 1. env injection: child sees PYTHONIOENCODING=utf-8 / PYTHONUTF8=1
    p1 = os.path.join(tmp, "enc.py")
    open(p1, "w").write(ENC_PROBE)
    out, _ = run_script(p1, {}, "r1", "n", None, 30, "")
    check("child gets PYTHONIOENCODING=utf-8", out["state"]["enc"] == "utf-8")
    check("child gets PYTHONUTF8=1", out["state"]["utf8mode"] == "1")

    # 2. non-ASCII round-trip (ensure_ascii=False, as a GBK host would emit)
    p2 = os.path.join(tmp, "cjk.py")
    open(p2, "w").write(CJK_PROBE)
    out, _ = run_script(p2, {}, "r2", "n", None, 30, "")
    check("CJK title intact", out["title"] == "中文标题·测试")
    check("CJK body intact", "不乱码" in out["event"] and "�" not in out["event"])

    # 3. notify: empty session_id passes through (channel falls back to user handle)
    cm = StubCM()
    eng = Engine(StubRepo(), StubInjector(cm), "default", cm)
    rule = EventRule(id="r3", name="n3", script=ScriptSpec(path=""),
                     dispatch=DispatchSpec(channel="qq", user_id="openid1", session_id=None))
    asyncio.run(eng._notify(rule, "hi"))
    check("session_id empty passthrough", cm.calls and cm.calls[0]["session_id"] == "")
    check("user_id preserved", cm.calls[0]["user_id"] == "openid1")

    cm2 = StubCM()
    eng2 = Engine(StubRepo(), StubInjector(cm2), "default", cm2)
    rule2 = EventRule(id="r4", name="n4", script=ScriptSpec(path=""),
                      dispatch=DispatchSpec(channel="qq", user_id="openid2", session_id="qq:c2c:x"))
    asyncio.run(eng2._notify(rule2, "hi"))
    check("explicit session_id passthrough", cm2.calls and cm2.calls[0]["session_id"] == "qq:c2c:x")

    passed = sum(1 for _, c in ok if c)
    print(f"\n{passed}/{len(ok)} passed")
    sys.exit(0 if passed == len(ok) else 1)

main()
