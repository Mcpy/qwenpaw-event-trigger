# -*- coding: utf-8 -*-
"""Bundled checker-script templates (single source of truth).

Served at GET /api/events/templates so agents can fetch ready-made
checkers instead of writing from scratch. Placeholders (__NAME__) are
substituted client-side before registration.
"""

TEMPLATES = [
    {
        "id": "btc",
        "name": "BTC 阈值监控(滞回)",
        "params": [
            {"k": "__SYMBOL__", "d": "BTCUSDT", "label": "交易对"},
            {"k": "__THRESHOLD__", "d": "100000", "label": "触发阈值"},
            {"k": "__RELEASE_PCT__", "d": "0.98", "label": "重武装比例(0.98=回踩2%)"},
        ],
        "script": '''#!/usr/bin/env python3
import json, os, urllib.request

SYMBOL = "__SYMBOL__"
THRESHOLD = float("__THRESHOLD__")
RELEASE = THRESHOLD * float("__RELEASE_PCT__")

state = json.loads(os.environ.get("EVENT_STATE") or "{}")
armed = bool(state.get("armed", True))
with urllib.request.urlopen("https://api.binance.com/api/v3/ticker/price?symbol=" + SYMBOL, timeout=10) as r:
    price = float(json.load(r)["price"])

if armed and price >= THRESHOLD:
    print(json.dumps({"triggered": True, "title": SYMBOL + " 突破 " + str(THRESHOLD), "event": SYMBOL + " 现价 " + str(price) + ",已突破阈值。请分析行情并决定是否值得提醒我。", "state": {"armed": False, "last_price": price}}, ensure_ascii=False))
elif (not armed) and price <= RELEASE:
    print(json.dumps({"triggered": False, "state": {"armed": True, "last_price": price}}, ensure_ascii=False))
else:
    print(json.dumps({"triggered": False, "state": {"armed": armed, "last_price": price}}, ensure_ascii=False))
''',
    },
    {
        "id": "http",
        "name": "HTTP 探测(非2xx/超时触发)",
        "params": [
            {"k": "__URL__", "d": "https://example.com/health", "label": "探测 URL"},
            {"k": "__TIMEOUT__", "d": "10", "label": "超时秒数"},
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
        "name": "文件变化监测",
        "params": [{"k": "__PATH__", "d": "/path/to/file", "label": "文件路径"}],
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
        "name": "端口存活(不可达触发)",
        "params": [
            {"k": "__HOST__", "d": "127.0.0.1", "label": "主机"},
            {"k": "__PORT__", "d": "8080", "label": "端口"},
            {"k": "__TIMEOUT__", "d": "5", "label": "超时秒数"},
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
        "name": "日志关键字(增量扫描)",
        "params": [
            {"k": "__FILE__", "d": "/var/log/app.log", "label": "日志文件"},
            {"k": "__KEYWORD__", "d": "ERROR", "label": "关键字"},
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
