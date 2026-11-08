"""trader_engine.py — self-contained chart analysis (no remote import)."""
from __future__ import annotations

import json
import math
import random
import urllib.request
from typing import Any

from flask import Blueprint, jsonify

last_errors: dict[str, str] = {}
DEFAULT_COINS = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "TON", "ADA", "AVAX", "LINK"]


def _http_json(url: str, timeout: int = 12):
    req = urllib.request.Request(url, headers={"User-Agent": "CryptoAI/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_rows(sym: str, interval: str = "1h", limit: int = 200):
    """OHLCV rows from Binance public API."""
    sym = (sym or "BTC").upper().replace("USDT", "")
    pair = f"{sym}USDT"
    url = f"https://api.binance.com/api/v3/klines?symbol={pair}&interval={interval}&limit={limit}"
    try:
        raw = _http_json(url)
        rows = [[int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5])] for x in raw]
        return rows, "binance"
    except Exception as e:
        last_errors[sym] = str(e)[:180]
        return [], "error"


def fetch_candles(sym: str, interval: str = "1h", limit: int = 240):
    """Dict form expected by post_card.market_state: keys t,o,h,l,c."""
    rows, src = fetch_rows(sym, interval, limit)
    if not rows:
        return None
    return {
        "t": [r[0] for r in rows],
        "o": [r[1] for r in rows],
        "h": [r[2] for r in rows],
        "l": [r[3] for r in rows],
        "c": [r[4] for r in rows],
        "v": [r[5] for r in rows],
        "src": src,
    }


def _rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(-period, 0):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    ag, al = sum(gains) / period, sum(losses) / period
    if al == 0:
        return 100.0
    rs = ag / al
    return 100 - (100 / (1 + rs))


def analyze(sym: str, candles=None) -> dict[str, Any]:
    """Trend, S/R, RSI, structure tags. No entry points."""
    if candles is None:
        rows, _ = fetch_rows(sym, "1h", 200)
        if not rows:
            return {"last": 0, "chg24h": 0, "res": 0, "sup": 0, "week_high": 0, "week_low": 0,
                    "rsi": 50, "trend": 0, "bias": 0, "tags": []}
        o = [r[1] for r in rows]; h = [r[2] for r in rows]; l = [r[3] for r in rows]; c = [r[4] for r in rows]
    else:
        if isinstance(candles, dict):
            o = [float(x) for x in candles["o"]]
            h = [float(x) for x in candles["h"]]
            l = [float(x) for x in candles["l"]]
            c = [float(x) for x in candles["c"]]
        else:
            o = [r[1] for r in candles]; h = [r[2] for r in candles]
            l = [r[3] for r in candles]; c = [r[4] for r in candles]
    n = len(c)
    last = float(c[-1])
    chg24 = (last / float(c[-25]) - 1) if n > 25 else 0.0
    window = min(48, n)
    res = max(h[-window:])
    sup = min(l[-window:])
    week_high = max(h[-min(168, n):])
    week_low = min(l[-min(168, n):])
    rsi = _rsi(c)
    ma_fast = sum(c[-12:]) / min(12, n)
    ma_slow = sum(c[-36:]) / min(36, n)
    trend = 1 if ma_fast > ma_slow * 1.002 else -1 if ma_fast < ma_slow * 0.998 else 0
    tags = []
    hh = h[-5] > h[-15] if n > 15 else False
    hl = l[-5] > l[-15] if n > 15 else False
    lh = h[-5] < h[-15] if n > 15 else False
    ll = l[-5] < l[-15] if n > 15 else False
    if hh and hl:
        tags.append({"id": "hh_hl", "fa": "ساختار صعودی (سقف و کف بالاتر)", "en": "Bullish structure (HH+HL)", "dir": 1})
        struct = 1
    elif lh and ll:
        tags.append({"id": "lh_ll", "fa": "ساختار نزولی (سقف و کف پایین‌تر)", "en": "Bearish structure (LH+LL)", "dir": -1})
        struct = -1
    elif hh or hl:
        tags.append({"id": "hh_partial", "fa": "تمایل ساختاری صعودی", "en": "Partial bullish structure", "dir": 1})
        struct = 1
    elif lh or ll:
        tags.append({"id": "lh_partial", "fa": "تمایل ساختاری نزولی", "en": "Partial bearish structure", "dir": -1})
        struct = -1
    else:
        tags.append({"id": "struct_flat", "fa": "ساختار نامشخص / رنج", "en": "Unclear / ranging structure", "dir": 0})
        struct = 0
    if last > res * 0.998:
        tags.append({"id": "bos_up", "fa": "BOS صعودی (نزدیک شکست سقف)", "en": "Near bullish BOS", "dir": 1})
    if last < sup * 1.002:
        tags.append({"id": "bos_dn", "fa": "BOS نزولی (نزدیک شکست کف)", "en": "Near bearish BOS", "dir": -1})
    width = (res - sup) / last if last else 0
    if width < 0.015:
        tags.append({"id": "squeeze", "fa": "فشردگی", "en": "Squeeze", "dir": 0})
    bias = struct if struct else trend
    if rsi > 70:
        bias = min(bias, 0)
    if rsi < 30:
        bias = max(bias, 0)
    return {
        "last": last, "chg24h": chg24, "res": float(res), "sup": float(sup),
        "week_high": float(week_high), "week_low": float(week_low),
        "rsi": float(rsi), "trend": trend, "bias": bias, "tags": tags,
    }


def simulate(a: dict, horizon: int = 24, paths: int = 2000, seed: int = 7) -> dict:
    p = float(a.get("last") or 0)
    if p <= 0:
        return {"p05": 0, "p25": 0, "median": 0, "p75": 0, "p95": 0,
                "touch": {"resistance": {"prob": 0}, "support": {"prob": 0}}}
    rng = random.Random(seed)
    vol = 0.012
    finals = []
    touch_r = touch_s = 0
    res, sup = float(a.get("res") or p), float(a.get("sup") or p)
    for _ in range(paths):
        x = p
        hit_r = hit_s = False
        for _h in range(horizon):
            x *= math.exp(rng.gauss(0, vol))
            if x >= res:
                hit_r = True
            if x <= sup:
                hit_s = True
        finals.append(x)
        if hit_r:
            touch_r += 1
        if hit_s:
            touch_s += 1
    finals.sort()
    def q(alpha):
        return finals[int(alpha * (len(finals) - 1))]
    return {
        "p05": q(0.05), "p25": q(0.25), "median": q(0.50),
        "p75": q(0.75), "p95": q(0.95),
        "touch": {
            "resistance": {"prob": touch_r / paths},
            "support": {"prob": touch_s / paths},
        },
    }


def scan_market(coins=None, interval="1h"):
    out = []
    for sym in (coins or DEFAULT_COINS):
        try:
            a = analyze(sym)
            if a["last"]:
                out.append({"sym": sym, **{k: a[k] for k in ("last", "chg24h", "rsi", "trend", "bias")}})
        except Exception as e:
            last_errors[sym] = str(e)[:120]
    return out


trader_bp = Blueprint("trader", __name__, url_prefix="/api/trader")


@trader_bp.get("/scan")
def _scan():
    return jsonify(scan_market())


@trader_bp.get("/setup/<symbol>")
def _setup(symbol):
    a = analyze(symbol)
    return jsonify(a)
