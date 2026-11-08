"""trader_engine.py — structure + volume/candle power + order-flow bias. No entry points."""
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
    rows, src = fetch_rows(sym, interval, limit)
    if not rows:
        return None
    return {
        "t": [r[0] for r in rows], "o": [r[1] for r in rows], "h": [r[2] for r in rows],
        "l": [r[3] for r in rows], "c": [r[4] for r in rows], "v": [r[5] for r in rows], "src": src,
    }


def _agg_delta(sym: str, limit: int = 800) -> dict | None:
    """Approximate buy/sell aggression from recent aggTrades (isBuyerMaker)."""
    sym = (sym or "BTC").upper().replace("USDT", "")
    url = f"https://api.binance.com/api/v3/aggTrades?symbol={sym}USDT&limit={limit}"
    try:
        raw = _http_json(url, timeout=8)
        buy = sell = 0.0
        for t in raw:
            q = float(t["q"])
            if t.get("m"):
                sell += q
            else:
                buy += q
        total = buy + sell
        if total <= 0:
            return None
        return {"buy": buy, "sell": sell, "delta": buy - sell, "delta_pct": (buy - sell) / total}
    except Exception as e:
        last_errors["delta"] = str(e)[:120]
        return None


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
    return 100 - (100 / (1 + ag / al))


def analyze(sym: str, candles=None) -> dict[str, Any]:
    """Structure + volume/candle power + order-flow bias. Directional only."""
    vol = None
    if candles is None:
        rows, _ = fetch_rows(sym, "1h", 200)
        if not rows:
            return {"last": 0, "chg24h": 0, "res": 0, "sup": 0, "week_high": 0, "week_low": 0,
                    "rsi": 50, "trend": 0, "bias": 0, "tags": []}
        o = [r[1] for r in rows]; h = [r[2] for r in rows]; l = [r[3] for r in rows]
        c = [r[4] for r in rows]; vol = [r[5] for r in rows]
    else:
        if isinstance(candles, dict):
            o = [float(x) for x in candles["o"]]; h = [float(x) for x in candles["h"]]
            l = [float(x) for x in candles["l"]]; c = [float(x) for x in candles["c"]]
            vol = [float(x) for x in candles.get("v") or []] or None
        else:
            o = [r[1] for r in candles]; h = [r[2] for r in candles]
            l = [r[3] for r in candles]; c = [r[4] for r in candles]
            vol = [r[5] for r in candles] if candles and len(candles[0]) > 5 else None

    n = len(c)
    last = float(c[-1])
    chg24 = (last / float(c[-25]) - 1) if n > 25 else 0.0
    window = min(48, n)
    res = max(h[-window:]); sup = min(l[-window:])
    week_high = max(h[-min(168, n):]); week_low = min(l[-min(168, n):])
    rsi = _rsi(c)
    ma_fast = sum(c[-12:]) / min(12, n)
    ma_slow = sum(c[-36:]) / min(36, n)
    trend = 1 if ma_fast > ma_slow * 1.002 else -1 if ma_fast < ma_slow * 0.998 else 0

    tags = []
    # --- structure ---
    hh = h[-5] > h[-15] if n > 15 else False
    hl = l[-5] > l[-15] if n > 15 else False
    lh = h[-5] < h[-15] if n > 15 else False
    ll = l[-5] < l[-15] if n > 15 else False
    if hh and hl:
        tags.append({"id": "hh_hl", "fa": "ساختار صعودی (سقف و کف بالاتر)", "en": "Bullish structure (HH+HL)", "dir": 1}); struct = 1
    elif lh and ll:
        tags.append({"id": "lh_ll", "fa": "ساختار نزولی (سقف و کف پایین‌تر)", "en": "Bearish structure (LH+LL)", "dir": -1}); struct = -1
    elif hh or hl:
        tags.append({"id": "hh_partial", "fa": "تمایل ساختاری صعودی", "en": "Partial bullish structure", "dir": 1}); struct = 1
    elif lh or ll:
        tags.append({"id": "lh_partial", "fa": "تمایل ساختاری نزولی", "en": "Partial bearish structure", "dir": -1}); struct = -1
    else:
        tags.append({"id": "struct_flat", "fa": "ساختار نامشخص / رنج", "en": "Unclear / ranging structure", "dir": 0}); struct = 0
    if last > res * 0.998:
        tags.append({"id": "bos_up", "fa": "BOS صعودی (نزدیک شکست سقف)", "en": "Near bullish BOS", "dir": 1})
    if last < sup * 1.002:
        tags.append({"id": "bos_dn", "fa": "BOS نزولی (نزدیک شکست کف)", "en": "Near bearish BOS", "dir": -1})

    # --- candle power (body vs range, close location) ---
    rng = max(h[-1] - l[-1], 1e-12)
    body = abs(c[-1] - o[-1])
    body_ratio = body / rng
    close_pos = (c[-1] - l[-1]) / rng  # 1=close at high (buyers), 0=at low (sellers)
    bull_candle = c[-1] >= o[-1]
    vol_bias = 0
    if body_ratio >= 0.55 and close_pos >= 0.7 and bull_candle:
        tags.append({"id": "candle_buy", "fa": "قدرت کندل خرید (بسته شدن نزدیک سقف)", "en": "Strong bullish candle (close near high)", "dir": 1})
        vol_bias += 1
    elif body_ratio >= 0.55 and close_pos <= 0.3 and not bull_candle:
        tags.append({"id": "candle_sell", "fa": "قدرت کندل فروش (بسته شدن نزدیک کف)", "en": "Strong bearish candle (close near low)", "dir": -1})
        vol_bias -= 1

    # --- volume vs average ---
    if vol and len(vol) >= 20:
        v_last = vol[-1]
        v_avg = sum(vol[-20:]) / 20
        v_ratio = v_last / v_avg if v_avg else 1
        # green vs red volume last 12 bars
        buy_v = sum(vol[i] for i in range(-12, 0) if c[i] >= o[i])
        sell_v = sum(vol[i] for i in range(-12, 0) if c[i] < o[i])
        vs = buy_v + sell_v
        if vs > 0:
            flow = (buy_v - sell_v) / vs
            if flow > 0.18:
                tags.append({"id": "vol_buy", "fa": "حجم به نفع خریداران", "en": "Volume favors buyers", "dir": 1})
                vol_bias += 1
            elif flow < -0.18:
                tags.append({"id": "vol_sell", "fa": "حجم به نفع فروشندگان", "en": "Volume favors sellers", "dir": -1})
                vol_bias -= 1
        if v_ratio >= 1.6:
            tags.append({"id": "vol_spike", "fa": "حجم غیرعادی (فعالیت بالا)", "en": "Unusual volume spike", "dir": 0})
            # high volume at resistance / support → absorption or breakout pressure
            near_res = abs(last - res) / last < 0.008 if last else False
            near_sup = abs(last - sup) / last < 0.008 if last else False
            if near_res and vol_bias < 0:
                tags.append({"id": "rej_res", "fa": "فشار فروش روی مقاومت (احتمال برگشت)", "en": "Sell pressure at resistance", "dir": -1})
                vol_bias -= 1
            elif near_res and vol_bias > 0:
                tags.append({"id": "brk_res", "fa": "فشار خرید روی مقاومت (احتمال شکست)", "en": "Buy pressure at resistance", "dir": 1})
                vol_bias += 1
            elif near_sup and vol_bias > 0:
                tags.append({"id": "def_sup", "fa": "دفاع خریداران روی حمایت", "en": "Buyers defending support", "dir": 1})
                vol_bias += 1
            elif near_sup and vol_bias < 0:
                tags.append({"id": "brk_sup", "fa": "فشار فروش روی حمایت (احتمال شکست)", "en": "Sell pressure at support", "dir": -1})
                vol_bias -= 1

    # --- live trade delta (footprint-style approximation) ---
    dlt = _agg_delta(sym)
    if dlt:
        dp = dlt["delta_pct"]
        if dp > 0.12:
            tags.append({"id": "flow_buy", "fa": "جریان سفارش: خریداران فعال‌تر", "en": "Order flow: buyers more active", "dir": 1})
            vol_bias += 1
        elif dp < -0.12:
            tags.append({"id": "flow_sell", "fa": "جریان سفارش: فروشندگان فعال‌تر", "en": "Order flow: sellers more active", "dir": -1})
            vol_bias -= 1

    width = (res - sup) / last if last else 0
    if width < 0.015:
        tags.append({"id": "squeeze", "fa": "فشردگی", "en": "Squeeze", "dir": 0})

    bias = struct if struct else trend
    if vol_bias > 0:
        bias = 1 if bias >= 0 else bias
    elif vol_bias < 0:
        bias = -1 if bias <= 0 else bias
    if rsi > 70:
        bias = min(bias, 0)
    if rsi < 30:
        bias = max(bias, 0)

    # prioritize flow/structure tags first for UI
    priority = {"hh_hl": 0, "lh_ll": 0, "hh_partial": 1, "lh_partial": 1, "bos_up": 2, "bos_dn": 2,
                "flow_buy": 3, "flow_sell": 3, "vol_buy": 4, "vol_sell": 4, "candle_buy": 5, "candle_sell": 5,
                "rej_res": 3, "brk_res": 3, "def_sup": 3, "brk_sup": 3}
    tags.sort(key=lambda t: priority.get(t["id"], 9))

    return {
        "last": last, "chg24h": chg24, "res": float(res), "sup": float(sup),
        "week_high": float(week_high), "week_low": float(week_low),
        "rsi": float(rsi), "trend": trend, "bias": bias, "tags": tags,
        "vol_bias": vol_bias,
    }


def simulate(a: dict, horizon: int = 24, paths: int = 2000, seed: int = 7) -> dict:
    p = float(a.get("last") or 0)
    if p <= 0:
        return {"p05": 0, "p25": 0, "median": 0, "p75": 0, "p95": 0,
                "touch": {"resistance": {"prob": 0}, "support": {"prob": 0}}}
    rng = random.Random(seed)
    vol = 0.012
    finals, touch_r, touch_s = [], 0, 0
    res, sup = float(a.get("res") or p), float(a.get("sup") or p)
    for _ in range(paths):
        x = p; hit_r = hit_s = False
        for _h in range(horizon):
            x *= math.exp(rng.gauss(0, vol))
            if x >= res: hit_r = True
            if x <= sup: hit_s = True
        finals.append(x)
        if hit_r: touch_r += 1
        if hit_s: touch_s += 1
    finals.sort()
    def q(alpha):
        return finals[int(alpha * (len(finals) - 1))]
    return {
        "p05": q(0.05), "p25": q(0.25), "median": q(0.50), "p75": q(0.75), "p95": q(0.95),
        "touch": {"resistance": {"prob": touch_r / paths}, "support": {"prob": touch_s / paths}},
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
    return jsonify(analyze(symbol))
