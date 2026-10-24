"""
floor.py — the "analysis floor": six AI agents, their live activity, and an honest track record.

Track record (no P&L, no trades — the project never gives entry points):
  • Backtest: for each of the last ~30 days, at the same hour, the chart engine's direction call
    (trend + patterns) for BTC, ETH and SOL is compared with the price 24 hours later, and the 24h
    Monte Carlo ranges are checked (did price land inside the 50% and 90% ranges?).
  • Live record: every day at TRACK_HOUR_UTC the combined call (chart + news) is saved and settled
    24 hours later. Kept in the pinned backup so restarts lose nothing.

Activity: built from real work the site does — news analysed, coins scanned, verdicts, ranges, posts.
"""
from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone

import numpy as np

COINS = ["BTC", "ETH", "SOL"]
TRACK_HOUR = int(os.environ.get("TRACK_HOUR_UTC", "16") or 16)
_lock = threading.Lock()
_cache = {"bt": None, "bt_at": 0.0, "scan": None, "scan_at": 0.0, "busy": set()}

AGENTS = [
    {"id": "scan", "n": "01", "name": "SCOUT", "role_fa": "اسکن ۲۴ کوین", "role_en": "Scans 24 coins", "shape": "square", "color": "#ff4fa3"},
    {"id": "news", "n": "02", "name": "HERALD", "role_fa": "خواندن خبرها", "role_en": "Reads the news", "shape": "pill", "color": "#22d3ee"},
    {"id": "trend", "n": "03", "name": "ATLAS", "role_fa": "روند و سطوح", "role_en": "Trend & levels", "shape": "hex", "color": "#a78bfa"},
    {"id": "risk", "n": "04", "name": "VEGA", "role_fa": "نوسان و محدوده", "role_en": "Volatility & range", "shape": "circle", "color": "#e5e7eb"},
    {"id": "judge", "n": "05", "name": "JUDGE", "role_fa": "تطبیق چارت و خبر", "role_en": "Chart vs news", "shape": "tri", "color": "#ffc94d"},
    {"id": "editor", "n": "06", "name": "QUILL", "role_fa": "نوشتن پست‌ها", "role_en": "Writes the posts", "shape": "blob", "color": "#33d39a"},
]


# ------------------------------------------------------------------ backtest
def _bt_one(sym: str, days: int = 30) -> list:
    import trader_engine as te
    rows, _ = te.fetch_rows(sym, "1h", 1000)
    k = np.array(rows, dtype=float)
    T, H, L, C, V = k[:, 0], k[:, 2], k[:, 3], k[:, 4], k[:, 5]
    out = []
    n = len(C)
    for d in range(1, days + 1):
        i = n - 1 - 24 * d                     # the moment of the call
        if i < 240 or i + 24 >= n:
            continue
        w = slice(i - 239, i + 1)
        cs = {"t": T[w].astype(np.int64), "o": k[w, 1], "h": H[w], "l": L[w], "c": C[w], "v": V[w]}
        a = te.analyze(sym, cs)
        sim = te.simulate(a, horizon=24, paths=1500, seed=11 + d)
        p0, p1 = float(C[i]), float(C[i + 24])
        move = p1 / p0 - 1
        out.append({"sym": sym, "ts": float(T[i]), "p0": p0, "p1": p1, "lean": int(a["bias"]),
                    "hit": (a["bias"] > 0 and move > 0) or (a["bias"] < 0 and move < 0) if a["bias"] else None,
                    "in50": sim["p25"] <= p1 <= sim["p75"], "in90": sim["p05"] <= p1 <= sim["p95"]})
    return out


def backtest() -> dict:
    """Cached 6 hours; computed in the background so no page waits for it."""
    if _cache["bt"] is not None and time.time() - _cache["bt_at"] < 6 * 3600:
        return _cache["bt"]
    if "bt" not in _cache["busy"]:
        _cache["busy"].add("bt")

        def run():
            try:
                rows = []
                for s in COINS:
                    try:
                        rows += _bt_one(s)
                    except Exception:
                        pass
                if rows:
                    _cache["bt"], _cache["bt_at"] = _summary(rows), time.time()
            finally:
                _cache["busy"].discard("bt")
        threading.Thread(target=run, daemon=True).start()
    return _cache["bt"] or {}


def _summary(rows: list) -> dict:
    calls = [r for r in rows if r.get("hit") is not None]
    hits = sum(1 for r in calls if r["hit"])
    by = {}
    for s in COINS:
        cs = [r for r in calls if r["sym"] == s]
        by[s] = {"calls": len(cs), "hits": sum(1 for r in cs if r["hit"])}
    rows_sorted = sorted(rows, key=lambda r: r["ts"])
    curve, acc = [], 0
    for r in [x for x in rows_sorted if x.get("hit") is not None]:
        acc += 1 if r["hit"] else -1
        curve.append(acc)
    return {"samples": len(rows), "calls": len(calls), "hits": hits,
            "rate": round(100 * hits / len(calls), 1) if calls else None,
            "in50": round(100 * sum(1 for r in rows if r["in50"]) / len(rows), 1) if rows else None,
            "in90": round(100 * sum(1 for r in rows if r["in90"]) / len(rows), 1) if rows else None,
            "by": by, "curve": curve[-90:],
            "recent": [{k: r[k] for k in ("sym", "ts", "p0", "p1", "lean", "hit")} for r in rows_sorted[-12:]]}


# ------------------------------------------------------------------ live record
def _track() -> list:
    import pro
    return pro.S.setdefault("track", [])


def record_today():
    import news_live
    import post_card
    scores = {a["key"]: a["score"] for a in (news_live.get_brief().get("assets") or [])}
    now = time.time()
    for s in COINS:
        key = s if s in ("BTC", "ETH") else "ALT"
        ms = post_card.market_state(s, scores.get(key, 0))
        if not ms:
            continue
        with _lock:
            _track().append({"sym": s, "ts": now, "p0": ms["price"], "lean": ms["lean"], "verdict": ms["verdict"],
                             "p05": ms["p05"], "p25": ms["p25"], "p75": ms["p75"], "p95": ms["p95"], "done": False})


def settle():
    import trader_engine as te
    changed = False
    for r in _track():
        if r["done"] or time.time() - r["ts"] < 24 * 3600:
            continue
        try:
            rows, _ = te.fetch_rows(r["sym"], "1h", 50)
        except Exception:
            continue
        target = r["ts"] + 24 * 3600
        after = [x for x in rows if x[0] >= target - 1800]
        if not after:
            continue
        p1 = float(after[0][4])
        move = p1 / r["p0"] - 1
        r.update(p1=p1, done=True, hit=(r["lean"] > 0 and move > 0) or (r["lean"] < 0 and move < 0) if r["lean"] else None,
                 in50=r["p25"] <= p1 <= r["p75"], in90=r["p05"] <= p1 <= r["p95"])
        changed = True
    with _lock:
        tr = _track()
        if len(tr) > 400:
            del tr[:len(tr) - 400]
    return changed


def live_summary() -> dict:
    done = [r for r in _track() if r.get("done")]
    return _summary(done) if done else {"samples": 0, "calls": 0}


def tick():
    """Called every minute: one live call per coin per day, settled 24 hours later."""
    import pro
    now = datetime.now(timezone.utc)
    pro.restore()
    day = now.strftime("%Y-%m-%d")
    if now.hour == TRACK_HOUR and pro.S.get("track_day") != day:
        pro.S["track_day"] = day
        try:
            record_today()
            pro.backup()
        except Exception:
            pass
    if now.minute % 15 == 3:
        try:
            if settle():
                pro.backup()
        except Exception:
            pass
    backtest()


# ------------------------------------------------------------------ scan (cached)
def scan():
    if _cache["scan"] is not None and time.time() - _cache["scan_at"] < 600:
        return _cache["scan"]
    if "scan" not in _cache["busy"]:
        _cache["busy"].add("scan")

        def run():
            try:
                import trader_engine as te
                res = te.scan_market()
                ok = [r for r in res if "error" not in r]
                if ok:
                    _cache["scan"], _cache["scan_at"] = ok, time.time()
            finally:
                _cache["busy"].discard("scan")
        threading.Thread(target=run, daemon=True).start()
    return _cache["scan"] or []


TAG_EN = None


def _tag_en(t):
    global TAG_EN
    if TAG_EN is None:
        import post_card
        TAG_EN = post_card.TAG_EN
    return TAG_EN.get(t, t)


# ------------------------------------------------------------------ the activity feed
def activity() -> list:
    """Real events from the last hours, newest first: [{ts, agent, kind, fa, en, d}]"""
    import news_live
    import post_card
    import telegram_bot
    ev = []
    b = news_live.get_brief()
    now = time.time()
    names = post_card.NAMES
    for n in (b.get("feed") or [])[:14]:
        ims = [x for x in n.get("im") or [] if x.get("d")]
        if not ims:
            ev.append({"ts": n["ts"], "agent": "news", "kind": "READ", "fa": n["t"][:90], "en": (n.get("en_t") or n["t"])[:90], "d": 0})
            continue
        x = max(ims, key=lambda y: y.get("s", 1))
        arrow = "▲" if x["d"] > 0 else "▼"
        ev.append({"ts": n["ts"], "agent": "news", "kind": "IMPACT", "d": x["d"],
                   "fa": f"{n['t'][:70]} ← {names.get(x['a'], x['a'])} {arrow}",
                   "en": f"{(n.get('en_t') or n['t'])[:70]} → {post_card.EN.get(x['a'], x['a'])} {arrow}"})
    sc = scan()
    t0 = _cache["scan_at"] or now
    for r in sc:
        for t in r.get("tags", [])[:1]:
            ev.append({"ts": t0 - 1, "agent": "scan", "kind": "PATTERN", "d": t.get("dir", 0),
                       "fa": f"{r['symbol']} · {t['fa']}", "en": f"{r['symbol']} · {t.get('en') or _tag_en(t['fa'])}"})
    scores = {a["key"]: a["score"] for a in (b.get("assets") or [])}
    for s in COINS:
        key = s if s in ("BTC", "ETH") else "ALT"
        try:
            ms = post_card.market_state(s, scores.get(key, 0))
        except Exception:
            ms = None
        if not ms:
            continue
        tr = {"up": ("صعودی", "up"), "down": ("نزولی", "down"), "range": ("خنثی", "flat")}[ms["trend"]]
        ev.append({"ts": now - 60, "agent": "trend", "kind": "TREND", "d": 1 if ms["trend"] == "up" else -1 if ms["trend"] == "down" else 0,
                   "fa": f"{s} روند {tr[0]} · مقاومت {post_card._money(ms['res'])} · حمایت {post_card._money(ms['sup'])}",
                   "en": f"{s} trend {tr[1]} · resistance {post_card._money(ms['res'])} · support {post_card._money(ms['sup'])}"})
        ev.append({"ts": now - 45, "agent": "risk", "kind": "RANGE", "d": 0,
                   "fa": f"{s} محدودهٔ ۲۴ ساعت: {post_card._money(ms['p25'])} تا {post_card._money(ms['p75'])} (۵۰٪)",
                   "en": f"{s} 24h range: {post_card._money(ms['p25'])}–{post_card._money(ms['p75'])} (50%)"})
        ev.append({"ts": now - 30, "agent": "judge", "kind": "VERDICT", "d": ms["lean"],
                   "fa": f"{s} · {post_card.VERDICT_FA[ms['verdict']]}", "en": f"{s} · {post_card.VERDICT_EN[ms['verdict']]}"})
    for p in telegram_bot.status().get("posted", [])[:4]:
        ev.append({"ts": p["at"], "agent": "editor", "kind": "POST", "d": 0,
                   "fa": "پست منتشر شد: " + p["text"][:70], "en": "Published: " + p["text"][:70]})
    ev.sort(key=lambda e: -e["ts"])
    return ev[:40]


def state() -> dict:
    import news_live
    b = news_live.get_brief()
    sc = scan()
    day = time.time() - 24 * 3600
    news_today = sum(1 for n in (b.get("feed") or []) if (n.get("ts") or 0) > day)
    return {
        "agents": AGENTS,
        "stats": {"coins": len(sc) or 24, "patterns": sum(len(r.get("tags", [])) for r in sc), "news": news_today,
                  "posts": len([p for p in __import__("telegram_bot").status().get("posted", [])])},
        "backtest": backtest(),
        "live": live_summary(),
        "activity": activity(),
        "updated": time.time(),
    }
