"""
trader_engine.py — CryptoAI Trader module for crypto-business

Crypto version of the "Trader" skill pack idea:
  1. Chart Scanner     -> scan_market()   scans many coins for chart patterns
  2. Setup sheet       -> analyze()       structure, key levels, findings
  3. Monte Carlo       -> simulate()      10,000 price paths, touch probabilities
  4. Telegram post     -> build_post() + send_for_approval()   (human approval first)

Project rule kept: NO entry points, NO buy/sell signals. Output is market-structure analysis.

Data: Binance public market-data endpoint (no API key needed).
Dependencies: requests, numpy, flask (optional, for the blueprint).

Env vars (set on the server, never in code or chat):
  TELEGRAM_BOT_TOKEN   bot token
  TELEGRAM_ADMIN_CHAT  chat id of the person who approves posts
"""
from __future__ import annotations

import os
import math
import time
import requests
import numpy as np

DEFAULT_COINS = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "TON", "ADA", "AVAX", "LINK",
                 "DOT", "TRX", "POL", "LTC", "NEAR", "APT", "ARB", "OP", "SUI", "PEPE",
                 "SHIB", "ATOM", "INJ", "FET"]


# ---------------------------------------------------------------- data
UA = {"User-Agent": "CryptoAI/1.0"}
_INTERVALS = {
    "1h": ("1h", "1H", "60", 3600), "4h": ("4h", "4H", "240", None),
    "15m": ("15m", "15m", "15", 900), "1d": ("1d", "1D", "D", 86400),
}


def _binance(host):
    def f(sym, iv, limit):
        r = requests.get(f"https://{host}/api/v3/klines", headers=UA, timeout=6,
                         params={"symbol": f"{sym}USDT", "interval": _INTERVALS[iv][0], "limit": limit})
        r.raise_for_status()
        return [[int(k[0]) // 1000, float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])] for k in r.json()]
    f.__name__ = host
    return f


def _okx(sym, iv, limit):
    r = requests.get("https://www.okx.com/api/v5/market/candles", headers=UA, timeout=6,
                     params={"instId": f"{sym}-USDT", "bar": _INTERVALS[iv][1], "limit": min(limit, 300)})
    r.raise_for_status()
    j = r.json()
    if j.get("code") != "0" or not j.get("data"):
        raise RuntimeError(f"okx: {j.get('msg') or 'no data'}")
    rows = [[int(k[0]) // 1000, float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])] for k in j["data"]]
    rows.reverse()
    return rows


def _bybit(sym, iv, limit):
    r = requests.get("https://api.bybit.com/v5/market/kline", headers=UA, timeout=6,
                     params={"category": "spot", "symbol": f"{sym}USDT", "interval": _INTERVALS[iv][2], "limit": limit})
    r.raise_for_status()
    j = r.json()
    if j.get("retCode") != 0:
        raise RuntimeError(f"bybit: {j.get('retMsg')}")
    rows = [[int(k[0]) // 1000, float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])] for k in j["result"]["list"]]
    rows.reverse()
    return rows


_SOURCES = [_binance("data-api.binance.vision"), _binance("api.binance.com"), _okx, _bybit]
_last_ok = {"i": 0}


def fetch_rows(sym: str, interval: "1h" | "4h" | "15m" | "1d" = "1h", limit: int = 300):
    order = list(range(len(_SOURCES)))
    order = order[_last_ok["i"]:] + order[:_last_ok["i"]]
    err = None
    for i in order:
        try:
            rows = _SOURCES[i](sym, interval, limit)
            if len(rows) < 50:
                raise RuntimeError("too few candles")
            _last_ok["i"] = i
            return rows, _SOURCES[i].__name__
        except Exception as e:
            err = e
    raise RuntimeError(f"all sources failed for {sym}: {err}")


def fetch_candles(sym: str, interval: str = "1h", limit: int = 300) -> dict:
    rows, _ = fetch_rows(sym, interval, limit)
    import numpy as np
    a = np.array(rows, dtype=float)
    return {"t": a[:, 0].astype(np.int64), "o": a[:, 1], "h": a[:, 2], "l": a[:, 3], "c": a[:, 4], "v": a[:, 5]}


def ema(arr, period):
    out = np.empty_like(arr, dtype=float)
    out[:] = np.nan
    if len(arr) < period:
        return out
    k = 2 / (period + 1)
    out[period - 1] = arr[:period].mean()
    for i in range(period, len(arr)):
        out[i] = arr[i] * k + out[i - 1] * (1 - k)
    return out


def rsi(arr, period=14):
    d = np.diff(arr, prepend=arr[0])
    up, dn = np.clip(d, 0, None), np.clip(-d, 0, None)
    au, ad = ema(up, period), ema(dn, period)
    rs = np.where(ad == 0, 100.0, au / np.where(ad == 0, 1e-12, ad))
    return 100 - (100 / (1 + rs))


def _swings(arr, lo, hi, low=True):
    out = []
    for i in range(lo + 3, hi - 3):
        nb = np.concatenate([arr[i - 3:i], arr[i + 1:i + 4]])
        if (low and arr[i] <= nb.min()) or (not low and arr[i] >= nb.max()):
            out.append(i)
    return out


def _pair(idx, arr, best_low=True):
    best = None
    for a in range(len(idx)):
        for b in range(a + 1, len(idx)):
            i, j = idx[a], idx[b]
            if j - i < 8 or abs(arr[i] - arr[j]) / arr[i] >= 0.012:
                continue
            s = arr[i] + arr[j]
            if best is None or (s < best[2] if best_low else s > best[2]):
                best = (i, j, s)
    return best


def _structure_bias(H, L, last, n, rh, rl, add):
    """HH/HL + BOS direction. Mutates tags via add(); returns struct in {-1,0,1}."""
    sh = _swings(H, max(0, n - 80), n, False)
    sl = _swings(L, max(0, n - 80), n, True)
    rh_sw, rl_sw = (sh[-4:] if len(sh) >= 2 else sh), (sl[-4:] if len(sl) >= 2 else sl)
    hh = hl = lh = ll = False
    if len(rh_sw) >= 2:
        hh, lh = H[rh_sw[-1]] > H[rh_sw[-2]], H[rh_sw[-1]] < H[rh_sw[-2]]
    if len(rl_sw) >= 2:
        hl, ll = L[rl_sw[-1]] > L[rl_sw[-2]], L[rl_sw[-1]] < L[rl_sw[-2]]
    lsh = float(H[rh_sw[-1]]) if rh_sw else float(rh)
    lsl = float(L[rl_sw[-1]]) if rl_sw else float(rl)
    bos_up, bos_dn = bool(rh_sw) and last > lsh, bool(rl_sw) and last < lsl
    struct = 0
    if hh and hl:
        add("hh_hl", "ساختار صعودی (سقف و کف بالاتر)", "Bullish structure (HH+HL)", 1); struct = 1
    elif lh and ll:
        add("lh_ll", "ساختار نزولی (سقف و کف پایین‌تر)", "Bearish structure (LH+LL)", -1); struct = -1
    if bos_up:
        add("bos_up", "BOS صعودی (شکست سقف ساختار)", "Bullish BOS", 1)
        struct = 1 if struct >= 0 else struct
    elif bos_dn:
        add("bos_dn", "BOS نزولی (شکست کف ساختار)", "Bearish BOS", -1)
        struct = -1 if struct <= 0 else struct
    return struct


def analyze(symbol: str, cs: dict) -> dict:
    C, H, L, V = cs["c"], cs["h"], cs["l"], cs["v"]
    n, last = len(C), C[-1]
    e20, e50 = ema(C, 20), ema(C, 50)
    r = rsi(C)

    rh, rl = H[n - 27:n - 3].max(), L[n - 27:n - 3].min()
    width = (rh - rl) / ((rh + rl) / 2)
    widths = []
    for i in range(24, n - 27, 6):
        a, b = H[i - 24:i].max(), L[i - 24:i].min()
        widths.append((a - b) / ((a + b) / 2))
    med_w = float(np.median(widths)) if widths else width

    tags = []
    add = lambda id_, fa, en, d: tags.append({"id": id_, "fa": fa, "en": en, "dir": d})
    tight = width < med_w * 0.85
    if tight and last > rh:
        add("bo_up", "شکست سقف رنج", "Range breakout (up)", 1)
    elif tight and last < rl:
        add("bo_dn", "شکست کف رنج", "Range breakdown", -1)
    elif width < med_w * 0.6:
        add("sqz", "فشردگی", "Volatility squeeze", 0)

    base = n - 60
    db = _pair(_swings(L, base, n, True), L, True)
    if db:
        i, j, _ = db
        neck = H[i:j + 1].max()
        if L[min(i, j)] <= L[base:].min() * 1.004 and neck / L[i] - 1 > 0.025 and (last > neck or j >= n - 20):
            if last > neck:
                add("dbl_b", "کف دوقلو (تأیید)", "Double bottom (confirmed)", 1)
            elif last > L[j]:
                add("dbl_b2", "کف دوقلو (در حال شکل‌گیری)", "Double bottom (forming)", 0)
    dt = _pair(_swings(H, base, n, False), H, False)
    if dt:
        i, j, _ = dt
        neck = L[i:j + 1].min()
        if max(H[i], H[j]) >= H[base:].max() * 0.996 and 1 - neck / H[i] > 0.025 and (last < neck or j >= n - 20):
            if last < neck:
                add("dbl_t", "سقف دوقلو (تأیید)", "Double top (confirmed)", -1)
            elif last < H[j]:
                add("dbl_t2", "سقف دوقلو (در حال شکل‌گیری)", "Double top (forming)", 0)

    for i in range(n - 6, n):
        if e20[i - 1] <= e50[i - 1] and e20[i] > e50[i]:
            add("x_up", "کراس طلایی EMA", "EMA golden cross", 1); break
        if e20[i - 1] >= e50[i - 1] and e20[i] < e50[i]:
            add("x_dn", "کراس مرگ EMA", "EMA death cross", -1); break
    if r > 70: add("ob", "اشباع خرید", "Overbought (RSI)", 0)
    if r < 30: add("os", "اشباع فروش", "Oversold (RSI)", 0)
    if V[-3:].max() > V[n - 53:n - 3].mean() * 2.3:
        add("vol", "حجم غیرعادی", "Volume spike", 0)

    struct = _structure_bias(H, L, last, n, rh, rl, add)
    trend = 0
    if last > e50[-1] and e20[-1] > e50[-1] and e50[-1] > e50[-12]: trend = 1
    if last < e50[-1] and e20[-1] < e50[-1] and e50[-1] < e50[-12]: trend = -1
    if struct:
        trend = struct
    score = sum(t["dir"] for t in tags) + trend + (2 * struct if struct else 0)
    bias = 1 if score >= 1 else -1 if score <= -1 else 0

    return {"symbol": symbol, "last": float(last), "chg24h": float(last / C[-25] - 1),
            "res": float(rh), "sup": float(rl), "week_high": float(H[-168:].max()),
            "week_low": float(L[-168:].min()), "rsi": float(r), "trend": trend,
            "bias": bias, "tags": tags, "_closes": C}


def simulate(a: dict, horizon: int = 24, paths: int = 10_000, block: int = 4, seed: int | None = None) -> dict:
    C = a["_closes"]
    rets = np.diff(np.log(C[-169:]))
    rets -= rets.mean()
    rng = np.random.default_rng(seed)
    nblocks = math.ceil(horizon / block)
    starts = rng.integers(0, len(rets) - block, size=(paths, nblocks))
    idx = (starts[:, :, None] + np.arange(block)).reshape(paths, -1)[:, :horizon]
    path = a["last"] * np.exp(np.cumsum(rets[idx], axis=1))
    fin, mx, mn = path[:, -1], path.max(axis=1), path.min(axis=1)
    q = np.quantile(fin, [.05, .25, .5, .75, .95])

    def touch(level):
        return float((mx >= level).mean() if level >= a["last"] else (mn <= level).mean())

    levels = {"resistance": a["res"], "support": a["sup"], "week_high": a["week_high"],
              "week_low": a["week_low"], "+5%": a["last"] * 1.05, "-5%": a["last"] * 0.95}
    return {"horizon_h": horizon, "paths": paths,
            "p05": float(q[0]), "p25": float(q[1]), "median": float(q[2]), "p75": float(q[3]), "p95": float(q[4]),
            "touch": {k: {"price": float(v), "prob": touch(v)} for k, v in levels.items()}}


def scan_market(coins=DEFAULT_COINS, interval="1h") -> list[dict]:
    out = []
    for s in coins:
        try:
            a = analyze(s, fetch_candles(s, interval))
            a.pop("_closes")
            out.append(a)
        except Exception as e:
            out.append({"symbol": s, "error": str(e)})
    return out


def fmt(p: float) -> str:
    a = abs(p)
    if a >= 1000: return f"{p:,.0f}"
    if a >= 10: return f"{p:.2f}"
    return f"{p:.4f}"


def build_post(a: dict, sim: dict) -> str:
    tags = "، ".join(t["fa"] for t in a["tags"][:4]) or "بدون الگوی خاص"
    direction = "صعودی" if a["bias"] > 0 else "نزولی" if a["bias"] < 0 else "خنثی"
    t = (f"#{a['symbol']} · ساختار بازار\n"
         f"قیمت: {fmt(a['last'])} ({a['chg24h']*100:+.2f}% 24h)\n"
         f"روند: {direction}\n"
         f"الگوها: {tags}\n"
         f"مقاومت ≈ {fmt(a['res'])} · حمایت ≈ {fmt(a['sup'])}\n"
         f"بازه محتمل ۲۴س (۵۰٪): {fmt(sim['p25'])} تا {fmt(sim['p75'])}\n"
         f"\n⚠️ این تحلیل آموزشی است و سیگنال خرید یا فروش نیست.\n#{a['symbol']} #کریپتو")
    return t


def send_for_approval(text: str, post_id: str) -> dict:
    token, chat = os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_ADMIN_CHAT"]
    kb = {"inline_keyboard": [[{"text": "✅ تأیید و انتشار", "callback_data": f"approve:{post_id}"},
                               {"text": "❌ رد", "callback_data": f"reject:{post_id}"}]]}
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      json={"chat_id": chat, "text": text, "reply_markup": kb}, timeout=15)
    r.raise_for_status()
    return r.json()


def run_cycle(coins=DEFAULT_COINS, max_posts: int = 3) -> list[str]:
    sent = []
    for s in coins:
        if len(sent) >= max_posts: break
        try:
            a = analyze(s, fetch_candles(s))
        except Exception:
            continue
        if not any(t["dir"] != 0 for t in a["tags"]):
            continue
        sim = simulate(a)
        pid = f"trader-{s}-{int(a['_closes'].size)}-{int(a['last']*1e6) % 10**8}"
        send_for_approval(build_post(a, sim), pid)
        sent.append(s)
    return sent


try:
    from flask import Blueprint, jsonify, request
    trader_bp = Blueprint("trader", __name__, url_prefix="/api/trader")

    @trader_bp.get("/scan")
    def api_scan():
        coins = request.args.get("coins")
        return jsonify(scan_market(coins.split(",") if coins else DEFAULT_COINS))

    @trader_bp.get("/setup/<symbol>")
    def api_setup(symbol):
        hz = int(request.args.get("horizon", 24))
        a = analyze(symbol.upper(), fetch_candles(symbol.upper()))
        sim = simulate(a, horizon=hz)
        closes = a.pop("_closes")
        return jsonify({**a, "simulation": sim, "post": build_post({**a, "_closes": closes}, sim)})
except ImportError:
    trader_bp = None


if __name__ == "__main__":
    import json
    a = analyze("BTC", fetch_candles("BTC"))
    sim = simulate(a)
    a.pop("_closes")
    print(json.dumps({**a, "simulation": sim}, ensure_ascii=False, indent=1))
