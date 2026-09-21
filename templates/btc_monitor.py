#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reference checker: BTC threshold with hysteresis arming (protocol demo).

Reads spot price from a public API. Fires when price crosses ABOVE the
threshold while armed; re-arms only after falling back below release.
State persists across runs via EVENT_STATE -> returned "state".

Protocol:
  IN : EVENT_STATE (JSON)  OUT: {"triggered": bool, "title": ..., "state": {...}}
"""

import json
import os
import urllib.request

SYMBOL = "BTCUSDT"
THRESHOLD = float(os.environ.get("BTC_THRESHOLD", "100000"))
RELEASE = THRESHOLD * 0.98  # hysteresis: re-arm 2% below


def fetch_price() -> float:
    url = f"https://api.binance.com/api/v3/ticker/price?symbol={SYMBOL}"
    with urllib.request.urlopen(url, timeout=10) as r:
        return float(json.load(r)["price"])


def main() -> None:
    state = json.loads(os.environ.get("EVENT_STATE") or "{}")
    armed = bool(state.get("armed", True))
    price = fetch_price()

    if armed and price >= THRESHOLD:
        print(json.dumps({
            "triggered": True,
            "title": f"BTC 突破 {THRESHOLD:.0f}",
            "event": f"BTC 现价 {price:.2f},已突破阈值 {THRESHOLD:.0f},请分析行情并决定是否值得提醒我。",
            "state": {"armed": False, "last_price": price},
        }, ensure_ascii=False))
    elif not armed and price <= RELEASE:
        # silent re-arm — not an event, just update state
        print(json.dumps({
            "triggered": False,
            "state": {"armed": True, "last_price": price},
        }, ensure_ascii=False))
    else:
        print(json.dumps({
            "triggered": False,
            "state": {"armed": armed, "last_price": price},
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()
