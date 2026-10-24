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
import requests
import numpy as np

BINANCE = "https://data-api.binance.vision/api/v3/klines"   # market-data-only host
DEFAULT_COINS = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "TON", "ADA", "AVAX", "LINK",
                 "DOT", "TRX", "POL", "LTC", "NEAR", "APT", "ARB", "OP", "SUI", "PEPE",
                 "SHIB", "ATOM", "INJ", "FET"]


# ---------------------------------------------------------------- data
def fetch_candles(symbol: str, interval: str = "1h", limit: int = 240) -> dict:
    """Returns dict of numpy arrays: t, o, h, l, c, v (oldest first)."""
    r = requests.get(BINANCE, params={"symbol": f"{symbol}USDT", "interval": interval, "limit": limit}, timeout=15)
    r.raise_for_status()
    k = np.array(r.json(), dtype=object)
    return {
        "t": k[:, 0].astype(np.int64) // 1000,
        "o": k[:, 1].astype(float), "h": k[:, 2].astype(float),
        "l": k[:, 3].astype(float), "c": k[:, 4].astype(float),
        "v": k[:, 5].astype(float),
    }


# ---------------------------------------------------------------- indicators
def ema(a: np.ndarray, n: int) -> np.ndarray:
    k, out, e = 2 / (n + 1), np.empty_like(a), a[0]
    for i, x in enumerate(a):
        e = x * k + e * (1 - k)
        out[i] = e
    return out


def rsi(c: np.ndarray, n: int = 14) -> float:
    d = np.diff(c)
    g, l = np.clip(d, 0, None), np.clip(-d, 0, None)
    ag, al = g[:n].mean(), l[:n].mean()
    for i in range(n, len(d)):
        ag = (ag * (n - 1) + g[i]) / n
        al = (al * (n - 1) + l[i]) / n
    return 100 - 100 / (1 + ag / (al or 1e-12))


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


# ---------------------------------------------------------------- setup sheet
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

    trend = 0
    if last > e50[-1] and e20[-1] > e50[-1] and e50[-1] > e50[-12]: trend = 1
    if last < e50[-1] and e20[-1] < e50[-1] and e50[-1] < e50[-12]: trend = -1
    score = sum(t["dir"] for t in tags) + trend
    bias = 1 if score >= 1 else -1 if score <= -1 else 0

    return {"symbol": symbol, "last": float(last), "chg24h": float(last / C[-25] - 1),
            "res": float(rh), "sup": float(rl), "week_high": float(H[-168:].max()),
            "week_low": float(L[-168:].min()), "rsi": float(r), "trend": trend,
            "bias": bias, "tags": tags, "_closes": C}


# ---------------------------------------------------------------- monte carlo
def simulate(a: dict, horizon: int = 24, paths: int = 10_000, block: int = 4, seed: int | None = None) -> dict:
    """Demeaned block bootstrap of the last 7 days of hourly returns (no directional assumption)."""
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


# ---------------------------------------------------------------- scanner
def scan_market(coins=DEFAULT_COINS, interval="1h") -> list[dict]:
    out = []
    for s in coins:
        try:
            a = analyze(s, fetch_candles(s, interval))
            a.pop("_closes")
            out.append(a)
        except Exception as e:                       # one bad coin must not stop the scan
            out.append({"symbol": s, "error": str(e)})
    return out


# ---------------------------------------------------------------- telegram
def fmt(p: float) -> str:
    a = abs(p)
    if a >= 1000: return f"{p:,.0f}"
    if a >= 10: return f"{p:.2f}"
    if a >= 1: return f"{p:.3f}"
    if a >= 0.01: return f"{p:.4f}"
    return f"{p:.3g}"


def build_post(a: dict, sim: dict | None) -> str:
    LRI, PDI = "⁦", "⁩"
    w = lambda x: LRI + x + PDI
    bias = {1: "صعودی 🟢", -1: "نزولی 🔴", 0: "خنثی ⚪️"}[a["bias"]]
    chg = "{:+.2f}%".format(a["chg24h"] * 100)
    t = (f"📊 {a['symbol']}/USDT · تحلیل ساختار بازار\n\n"
         f"قیمت: {w(fmt(a['last']))}\nتغییر ۲۴ ساعت: {w(chg)}\n"
         f"جهت ساختار: {bias}\n")
    if a["tags"]:
        t += "\nالگوهای شناسایی‌شده:\n" + "\n".join("• " + x["fa"] for x in a["tags"]) + "\n"
    t += f"\nسطوح کلیدی:\nسقف رنج {w(fmt(a['res']))} · کف رنج {w(fmt(a['sup']))}\n"
    if sim:
        hz = "۲۴ ساعت" if sim["horizon_h"] == 24 else f"{sim['horizon_h']} ساعت"
        t += (f"\nشبیه‌سازی ۱۰٬۰۰۰ مسیر برای {hz} آینده:\n"
              f"۵۰٪ مسیرها بین {w(fmt(sim['p25']))} و {w(fmt(sim['p75']))} بسته شدند.\n"
              f"احتمال لمس سقف رنج: {round(sim['touch']['resistance']['prob']*100)}٪ · "
              f"احتمال لمس کف رنج: {round(sim['touch']['support']['prob']*100)}٪\n")
    t += f"\n⚠️ این تحلیل آموزشی است و سیگنال خرید یا فروش نیست.\n#{a['symbol']} #کریپتو"
    return t


def send_for_approval(text: str, post_id: str) -> dict:
    """Sends the draft to the admin with Approve / Reject buttons.
    Your existing webhook handles callback_data 'approve:<id>' / 'reject:<id>' and publishes to the channel."""
    token, chat = os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_ADMIN_CHAT"]
    kb = {"inline_keyboard": [[{"text": "✅ تأیید و انتشار", "callback_data": f"approve:{post_id}"},
                               {"text": "❌ رد", "callback_data": f"reject:{post_id}"}]]}
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      json={"chat_id": chat, "text": text, "reply_markup": kb}, timeout=15)
    r.raise_for_status()
    return r.json()


def run_cycle(coins=DEFAULT_COINS, max_posts: int = 3) -> list[str]:
    """For the scheduler: scan, pick coins with confirmed patterns, draft posts, send for approval."""
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


# ---------------------------------------------------------------- flask blueprint
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
except ImportError:          # flask not installed: module still usable on its own
    trader_bp = None


if __name__ == "__main__":
    import json
    a = analyze("BTC", fetch_candles("BTC"))
    sim = simulate(a)
    a.pop("_closes")
    print(json.dumps({**a, "simulation": sim}, ensure_ascii=False, indent=1))
