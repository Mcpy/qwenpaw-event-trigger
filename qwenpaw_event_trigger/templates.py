# -*- coding: utf-8 -*-
"""Bundled checker-script templates (single source of truth).

Each template declares a top-level `CONFIG = {...}` literal dict (ast-parseable,
never executed) holding user-tunable parameters. Placeholders (__NAME__) are
substituted at creation time; after that, params are edited via the CONFIG
block (UI auto-form / PUT config), which re-registers on enable by design.
"""

TEMPLATES = [
    {
        "id": "stock",
        "name": {"zh": "股价阈值监控(滞回,双边界)", "en": "Stock price threshold (hysteresis, dual-bound)"},
        "params": [
            {"k": "__TICKER__", "d": "NVDA", "label": {"zh": "股票代码(如 NVDA、AAPL、TSLA)", "en": "Ticker (NVDA, AAPL, TSLA)"}},
            {"k": "__THRESHOLD_UP__", "d": "200", "label": {"zh": "上界:涨破触发", "en": "Upper bound: fire when price >= up"}},
            {"k": "__THRESHOLD_DOWN__", "d": "180", "label": {"zh": "下界:跌破触发", "en": "Lower bound: fire when price <= down"}},
        ],
        "prompt": {"zh": "行情事件:[{title}] {event}\n请先用 Skill 工具阅读 event-tasks 技能,然后:1) 拉取最新行情,判断突破有效性(还是噪声);2) 决定是否提醒用户,若提醒则给出简要分析与依据;3) 若需继续观望,按技能中的『触发-演化循环』更新本任务 CONFIG 并重新启用。", "en": "Market event: [{title}] {event}\nFirst read the event-tasks skill via the Skill tool, then: 1) fetch latest quotes and judge whether the breakout is real; 2) decide whether to notify the user; 3) if watching continues, update this task's CONFIG per the fire-evolve loop in the skill and re-enable."},
        "script": '''#!/usr/bin/env python3
import json, os, urllib.request

CONFIG = {
    "ticker": "__TICKER__",
    "threshold_up": __THRESHOLD_UP__,     # 涨破触发
    "threshold_down": __THRESHOLD_DOWN__, # 跌破触发
}

state = json.loads(os.environ.get("EVENT_STATE") or "{}")
armed = bool(state.get("armed", True))
up = float(CONFIG["threshold_up"])
down = float(CONFIG["threshold_down"])
url = "https://query1.finance.yahoo.com/v8/finance/chart/" + CONFIG["ticker"] + "?interval=1d&range=1d"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req, timeout=10) as r:
    meta = json.load(r)["chart"]["result"][0]["meta"]
price = float(meta["regularMarketPrice"])

if armed and (price >= up or price <= down):
    direction = "涨破" if price >= up else "跌破"
    bound = up if price >= up else down
    print(json.dumps({"triggered": True, "title": CONFIG["ticker"] + " " + direction + " " + str(bound), "event": CONFIG["ticker"] + " 现价 " + str(price) + " USD," + direction + "边界 " + str(bound) + "(当前监控区间 " + str(down) + "~" + str(up) + ")。", "state": {"armed": False, "last_price": price}}, ensure_ascii=False))
else:
    print(json.dumps({"triggered": False, "state": {"armed": armed, "last_price": price}}, ensure_ascii=False))
''',
    },
    {
        "id": "http",
        "name": {"zh": "HTTP 探测(非2xx/超时触发)", "en": "HTTP probe (fire on non-2xx/timeout)"},
        "params": [
            {"k": "__URL__", "d": "https://example.com/health", "label": {"zh": "探测 URL", "en": "URL to probe"}},
            {"k": "__TIMEOUT__", "d": "10", "label": {"zh": "超时秒数", "en": "Timeout seconds"}},
        ],
        "prompt": {"zh": "事件:[{title}] {event}\n请先阅读 event-tasks 技能,然后探测该服务实际状态并向用户汇报(含恢复/故障判定与建议)。", "en": "Event: [{title}] {event}\nRead the event-tasks skill first, then probe the service and report status (recovered/down) with suggestions."},
        "script": '''#!/usr/bin/env python3
import json, os, urllib.request

CONFIG = {
    "url": "__URL__",
    "timeout": __TIMEOUT__,
}

try:
    with urllib.request.urlopen(CONFIG["url"], timeout=CONFIG["timeout"]) as r:
        code = r.status
except Exception as exc:
    print(json.dumps({"triggered": True, "title": "HTTP 探测失败", "event": CONFIG["url"] + " 不可达: " + repr(exc)}, ensure_ascii=False))
    raise SystemExit(0)
if code >= 400:
    print(json.dumps({"triggered": True, "title": "HTTP 状态异常", "event": CONFIG["url"] + " 返回 " + str(code)}, ensure_ascii=False))
else:
    print(json.dumps({"triggered": False}, ensure_ascii=False))
''',
    },
    {
        "id": "file",
        "name": {"zh": "文件变化监测", "en": "File change monitor"},
        "params": [{"k": "__PATH__", "d": "/path/to/file", "label": {"zh": "文件路径", "en": "File path"}}],
        "prompt": {"zh": "文件事件:[{title}] {event}\n请先阅读 event-tasks 技能,然后查看该文件的变化内容并向用户汇报要点。", "en": "File event: [{title}] {event}\nRead the event-tasks skill first, inspect what changed in the file and report the key points."},
        "script": '''#!/usr/bin/env python3
import json, os

CONFIG = {"path": "__PATH__"}
st = json.loads(os.environ.get("EVENT_STATE") or "{}")
try:
    s = os.stat(CONFIG["path"])
    fp = str(s.st_mtime_ns) + ":" + str(s.st_size)
except OSError as exc:
    print(json.dumps({"triggered": True, "title": "文件不可访问", "event": CONFIG["path"] + ": " + repr(exc)}, ensure_ascii=False))
    raise SystemExit(0)
prev = st.get("fingerprint")
if prev is not None and prev != fp:
    print(json.dumps({"triggered": True, "title": "文件发生变化", "event": CONFIG["path"] + " 已被修改(mtime/size 变化)。", "state": {"fingerprint": fp}}, ensure_ascii=False))
else:
    print(json.dumps({"triggered": False, "state": {"fingerprint": fp}}, ensure_ascii=False))
''',
    },
    {
        "id": "port",
        "name": {"zh": "端口存活(不可达触发)", "en": "Port alive (fire when unreachable)"},
        "params": [
            {"k": "__HOST__", "d": "127.0.0.1", "label": {"zh": "主机", "en": "Host"}},
            {"k": "__PORT__", "d": "8080", "label": {"zh": "端口", "en": "Port"}},
            {"k": "__TIMEOUT__", "d": "5", "label": {"zh": "超时秒数", "en": "Timeout seconds"}},
        ],
        "prompt": {"zh": "事件:[{title}] {event}\n请先阅读 event-tasks 技能,然后检查该服务进程/端口状态并向用户汇报(含排查建议)。", "en": "Event: [{title}] {event}\nRead the event-tasks skill first, check the service/port status and report with troubleshooting suggestions."},
        "script": '''#!/usr/bin/env python3
import json, socket

CONFIG = {"host": "__HOST__", "port": __PORT__, "timeout": __TIMEOUT__}
try:
    with socket.create_connection((CONFIG["host"], CONFIG["port"]), timeout=CONFIG["timeout"]):
        print(json.dumps({"triggered": False}, ensure_ascii=False))
except Exception as exc:
    print(json.dumps({"triggered": True, "title": "端口不可达", "event": CONFIG["host"] + ":" + str(CONFIG["port"]) + " 连接失败: " + repr(exc)}, ensure_ascii=False))
''',
    },
    {
        "id": "log",
        "name": {"zh": "日志关键字(增量扫描)", "en": "Log keyword (incremental scan)"},
        "params": [
            {"k": "__FILE__", "d": "/var/log/app.log", "label": {"zh": "日志文件", "en": "Log file"}},
            {"k": "__KEYWORD__", "d": "ERROR", "label": {"zh": "关键字", "en": "Keyword"}},
        ],
        "prompt": {"zh": "日志事件:[{title}] {event}\n请先阅读 event-tasks 技能,然后分析命中的日志行,向用户汇报错误原因与处理建议。", "en": "Log event: [{title}] {event}\nRead the event-tasks skill first, analyze the matched log lines and report root cause with suggestions."},
        "script": '''#!/usr/bin/env python3
import json, os

CONFIG = {"file": "__FILE__", "keyword": "__KEYWORD__"}
st = json.loads(os.environ.get("EVENT_STATE") or "{}")
offset = int(st.get("offset", 0))
try:
    size = os.path.getsize(CONFIG["file"])
except OSError as exc:
    print(json.dumps({"triggered": True, "title": "日志文件不可读", "event": CONFIG["file"] + ": " + repr(exc)}, ensure_ascii=False))
    raise SystemExit(0)
if size < offset:
    offset = 0  # rotated
hits = []
with open(CONFIG["file"], "r", encoding="utf-8", errors="replace") as f:
    f.seek(offset)
    for line in f:
        if CONFIG["keyword"] in line:
            hits.append(line.strip()[:200])
    offset = f.tell()
if hits:
    more = " (+" + str(len(hits) - 5) + " more)" if len(hits) > 5 else ""
    print(json.dumps({"triggered": True, "title": "日志命中 " + CONFIG["keyword"], "event": chr(10).join(hits[:5]) + more, "state": {"offset": offset}}, ensure_ascii=False))
else:
    print(json.dumps({"triggered": False, "state": {"offset": offset}}, ensure_ascii=False))
''',
    },
]
