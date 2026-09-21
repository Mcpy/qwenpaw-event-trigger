# -*- coding: utf-8 -*-
"""Bundled checker-script templates (single source of truth).

Served at GET /api/events/templates so agents can fetch ready-made
checkers instead of writing from scratch. Placeholders (__NAME__) are
substituted client-side before registration.
"""

TEMPLATES = [
    {
        "id": "stock",
        "name": {"zh": "股价阈值监控(滞回)", "en": "Stock price threshold (hysteresis)"},
        "params": [
            {"k": "__TICKER__", "d": "NVDA", "label": {"zh": "股票代码(如 NVDA、AAPL、TSLA)", "en": "Ticker (NVDA, AAPL, TSLA)"}},
            {"k": "__THRESHOLD__", "d": "200", "label": {"zh": "触发阈值", "en": "Threshold"}},
            {"k": "__RELEASE_PCT__", "d": "0.98", "label": {"zh": "重武装比例(0.98=回踩2%)", "en": "Release ratio (0.98 = re-arm at 2% pullback)"}},
        ],
        "script": '''#!/usr/bin/env python3
import json, os, urllib.request

TICKER = "__TICKER__"
THRESHOLD = float("__THRESHOLD__")
RELEASE = THRESHOLD * float("__RELEASE_PCT__")

state = json.loads(os.environ.get("EVENT_STATE") or "{}")
armed = bool(state.get("armed", True))
url = "https://query1.finance.yahoo.com/v8/finance/chart/" + TICKER + "?interval=1d&range=1d"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req, timeout=10) as r:
    meta = json.load(r)["chart"]["result"][0]["meta"]
price = float(meta["regularMarketPrice"])

if armed and price >= THRESHOLD:
    print(json.dumps({"triggered": True, "title": TICKER + " 突破 " + str(THRESHOLD), "event": TICKER + " 现价 " + str(price) + " USD,已突破阈值 " + str(THRESHOLD) + "。请分析行情并决定是否值得提醒我。", "state": {"armed": False, "last_price": price}}, ensure_ascii=False))
elif (not armed) and price <= RELEASE:
    print(json.dumps({"triggered": False, "state": {"armed": True, "last_price": price}}, ensure_ascii=False))
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
        "script": '''#!/usr/bin/env python3
import json, urllib.request

URL = "__URL__"
try:
    with urllib.request.urlopen(URL, timeout=__TIMEOUT__) as r:
        code = r.status
except Exception as exc:
    print(json.dumps({"triggered": True, "title": "HTTP 探测失败", "event": URL + " 不可达: " + repr(exc)}, ensure_ascii=False))
    raise SystemExit(0)
if code >= 400:
    print(json.dumps({"triggered": True, "title": "HTTP 状态异常", "event": URL + " 返回 " + str(code)}, ensure_ascii=False))
else:
    print(json.dumps({"triggered": False}, ensure_ascii=False))
''',
    },
    {
        "id": "file",
        "name": {"zh": "文件变化监测", "en": "File change monitor"},
        "params": [{"k": "__PATH__", "d": "/path/to/file", "label": {"zh": "文件路径", "en": "File path"}}],
        "script": '''#!/usr/bin/env python3
import json, os

PATH = "__PATH__"
st = json.loads(os.environ.get("EVENT_STATE") or "{}")
try:
    s = os.stat(PATH)
    fp = str(s.st_mtime_ns) + ":" + str(s.st_size)
except OSError as exc:
    print(json.dumps({"triggered": True, "title": "文件不可访问", "event": PATH + ": " + repr(exc)}, ensure_ascii=False))
    raise SystemExit(0)
prev = st.get("fingerprint")
if prev is not None and prev != fp:
    print(json.dumps({"triggered": True, "title": "文件发生变化", "event": PATH + " 已被修改(mtime/size 变化)。", "state": {"fingerprint": fp}}, ensure_ascii=False))
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
        "script": '''#!/usr/bin/env python3
import json, socket

HOST, PORT, TIMEOUT = "__HOST__", __PORT__, __TIMEOUT__
try:
    with socket.create_connection((HOST, PORT), timeout=TIMEOUT):
        print(json.dumps({"triggered": False}, ensure_ascii=False))
except Exception as exc:
    print(json.dumps({"triggered": True, "title": "端口不可达", "event": HOST + ":" + str(PORT) + " 连接失败: " + repr(exc)}, ensure_ascii=False))
''',
    },
    {
        "id": "log",
        "name": {"zh": "日志关键字(增量扫描)", "en": "Log keyword (incremental scan)"},
        "params": [
            {"k": "__FILE__", "d": "/var/log/app.log", "label": {"zh": "日志文件", "en": "Log file"}},
            {"k": "__KEYWORD__", "d": "ERROR", "label": {"zh": "关键字", "en": "Keyword"}},
        ],
        "script": '''#!/usr/bin/env python3
import json, os

FILE, KEY = "__FILE__", "__KEYWORD__"
st = json.loads(os.environ.get("EVENT_STATE") or "{}")
offset = int(st.get("offset", 0))
try:
    size = os.path.getsize(FILE)
except OSError as exc:
    print(json.dumps({"triggered": True, "title": "日志文件不可读", "event": FILE + ": " + repr(exc)}, ensure_ascii=False))
    raise SystemExit(0)
if size < offset:
    offset = 0  # rotated
hits = []
with open(FILE, "r", encoding="utf-8", errors="replace") as f:
    f.seek(offset)
    for line in f:
        if KEY in line:
            hits.append(line.strip()[:200])
    offset = f.tell()
if hits:
    more = " (+" + str(len(hits) - 5) + " more)" if len(hits) > 5 else ""
    print(json.dumps({"triggered": True, "title": "日志命中 " + KEY, "event": chr(10).join(hits[:5]) + more, "state": {"offset": offset}}, ensure_ascii=False))
else:
    print(json.dumps({"triggered": False, "state": {"offset": offset}}, ensure_ascii=False))
''',
    },
]
