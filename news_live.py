"""
news_live.py — live crypto news for the radio globe.

Every REFRESH_SEC the server:
  1. reads public RSS feeds (no keys needed),
  2. sends each headline to the station of the place it is about (keyword rules),
  3. asks the site's AI (Groq) once for Persian titles/summaries and "up/down" notes per station.
Results are cached in memory; requests never wait for a refresh (it runs in a background thread).
If feeds or AI fail, the last good result (or the researched snapshot in static/data/stations.json) is served.
"""
from __future__ import annotations

import copy
import html
import json
import os
import re
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

import ai_client

BASE = os.path.dirname(os.path.abspath(__file__))
SNAPSHOT = os.path.join(BASE, "static", "data", "stations.json")
REFRESH_SEC = int(os.environ.get("NEWS_REFRESH_SEC", 600))
MAX_AGE_H = 72
PER_STATION = 5

FEEDS = [
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("Cointelegraph", "https://cointelegraph.com/rss"),
    ("Decrypt", "https://decrypt.co/feed"),
    ("The Block", "https://www.theblock.co/rss.xml"),
    ("Bitcoin Magazine", "https://bitcoinmagazine.com/.rss/full/"),
    ("CryptoSlate", "https://cryptoslate.com/feed/"),
]
UA = {"User-Agent": "Mozilla/5.0 (compatible; CryptoAI-Radio/1.0)"}

# First match wins: specific places before topic-based desks.
RULES = [
    ("sansalvador", ["el salvador", "bukele", "salvadoran"]),
    ("nairobi", ["kenya", "nairobi", "east africa"]),
    ("lagos", ["nigeria", "lagos", "ghana", "south africa", "africa"]),
    ("seoul", ["korea", "upbit", "bithumb", "seoul"]),
    ("tokyo", ["japan", "tokyo", "metaplanet", "yen "]),
    ("hk", ["hong kong", "hkma", "china", "chinese", "beijing", "yuan"]),
    ("mumbai", ["india", "mumbai", "wazirx", "coindcx", "rupee"]),
    ("dubai", ["dubai", "uae", "abu dhabi", "emirates", "saudi", "middle east", "bahrain", "qatar", "vara"]),
    ("london", ["u.k.", " uk ", "uk's", "britain", "british", "fca", "london", "bank of england"]),
    ("paris", ["mica", "european", "europe", " eu ", "eu's", "ecb", "france", "french", "germany", "german", "digital euro", "italy", "spain"]),
    ("saopaulo", ["brazil", "argentina", "latin america", "latam", "mexico", "colombia", "milei"]),
    ("dc", [" sec ", "sec's", "securities and exchange", "federal reserve", " fed ", "fed's", "powell", "congress", "senate",
            "white house", "trump", "treasury", "cftc", "clarity act", "genius act", "midterm", "washington", "lawmakers", "irs"]),
    ("zug", ["ethereum", "vitalik", " ether ", " eth ", "glamsterdam", "layer-2", "layer 2", "switzerland", "swiss"]),
    ("nyc", ["etf", "blackrock", "ibit", "fidelity", "nasdaq", "wall street", "s&p", "coinbase", "microstrategy", "strategy",
             "jpmorgan", "goldman", "nyse", "new york", "liquidat", "bitcoin", "btc", "price", "market"]),
]

_lock = threading.Lock()
_state = {"data": None, "at": 0.0, "running": False, "error": None, "feeds_ok": [], "ai": False}


def _text(el, tag):
    x = el.find(tag)
    return (x.text or "").strip() if x is not None and x.text else ""


def _clean(s: str, n: int) -> str:
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    s = re.sub(r"\s+", " ", s).strip()
    return s[:n]


def _fetch_feed(name_url):
    name, url = name_url
    try:
        r = requests.get(url, headers=UA, timeout=12)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        out = []
        for it in root.iter("item"):
            title = _clean(_text(it, "title"), 220)
            link = _text(it, "link")
            pub = _text(it, "pubDate")
            try:
                ts = parsedate_to_datetime(pub).astimezone(timezone.utc).timestamp() if pub else None
            except Exception:
                ts = None
            if not title or not link or not ts:
                continue
            out.append({"title": title, "desc": _clean(_text(it, "description"), 300), "url": link, "ts": ts, "source": name})
        return name, out
    except Exception:
        return name, None


def classify(title: str, desc: str) -> str:
    hay = " " + (title + " " + desc).lower() + " "
    for sid, words in RULES:
        if any(w in hay for w in words):
            return sid
    return "nyc"


def _dedupe(items):
    seen, out = set(), []
    for it in sorted(items, key=lambda x: -x["ts"]):
        key = re.sub(r"[^a-z0-9]", "", it["title"].lower())[:60]
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def _ai_enrich(by_station: dict, market_hint: str):
    """One AI call: Persian title + summary per item, and up to 3 impact notes per station."""
    payload = {sid: [{"i": k, "title": it["title"], "desc": it["desc"][:220]} for k, it in enumerate(items)]
               for sid, items in by_station.items() if items}
    if not payload:
        return {}
    prompt = f"""You translate and analyse crypto news for a Persian radio website.
Input: news items grouped by station id. Use ONLY the information in each title/desc. Do not add facts, numbers or names that are not there.
Return ONLY JSON in this exact shape:
{{"<station id>": {{"items": [{{"i": <index>, "t": "Persian title, max 14 words", "b": "Persian summary, 1-2 sentences, only from the given text"}}],
                  "notes": [{{"c": ["BTC"], "dir": "up"|"down"|"mixed", "n": "Persian, max 25 words: likely market effect", "w": "Persian reason/timing, max 12 words"}}]}}}}
Rules for notes: max 3 per station; no buy/sell advice, no targets, no entry points; if no real market effect use "mixed".
Market context: {market_hint}
DATA:
{json.dumps(payload, ensure_ascii=False)}"""
    raw = ai_client.ask(prompt, json_mode=True, max_tokens=6000, timeout=120)
    m = re.search(r"\{[\s\S]*\}", raw)
    return json.loads(m.group(0) if m else raw)


def _market_hint():
    try:
        import trader_engine
        parts = []
        for s in ("BTC", "ETH"):
            rows, src = trader_engine.fetch_rows(s, "1h", 25)
            parts.append(f"{s} {rows[-1][4]:,.2f} USD ({(rows[-1][4] / rows[0][4] - 1) * 100:+.2f}% 24h, {src})")
        return "; ".join(parts)
    except Exception:
        return "unknown"


def _build():
    with open(SNAPSHOT, encoding="utf-8") as f:
        snap = json.load(f)
    with ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(_fetch_feed, FEEDS))
    feeds_ok = [n for n, items in results if items]
    items = [it for _, lst in results if lst for it in lst]
    cutoff = time.time() - MAX_AGE_H * 3600
    items = _dedupe([it for it in items if it["ts"] >= cutoff])
    if not items:
        raise RuntimeError("no feed answered")

    station_ids = {s["id"] for s in snap["stations"]}
    by_station = {sid: [] for sid in station_ids}
    for it in items:
        sid = classify(it["title"], it["desc"])
        if sid in by_station and len(by_station[sid]) < PER_STATION:
            by_station[sid].append(it)

    enriched, ai_ok = {}, False
    if ai_client.provider():
        try:
            enriched = _ai_enrich(by_station, _market_hint())
            ai_ok = True
        except Exception as e:
            _state["error"] = f"AI: {e}"

    data = copy.deepcopy(snap)
    for st in data["stations"]:
        live = by_station.get(st["id"]) or []
        if not live:
            st["live"] = False
            continue
        e = enriched.get(st["id"]) or {}
        tr = {x.get("i"): x for x in (e.get("items") or []) if isinstance(x, dict)}
        news = []
        for k, it in enumerate(live):
            fa = tr.get(k) or {}
            news.append({
                "d": datetime.fromtimestamp(it["ts"], timezone.utc).strftime("%d %b %H:%M UTC"),
                "ts": it["ts"],
                "t": fa.get("t") or it["title"],
                "b": fa.get("b") or it["desc"],
                "en": it["title"] + ". " + it["desc"],
                "lang": "fa" if fa.get("t") else "en",
                "source": {"name": it["source"], "url": it["url"]},
            })
        st["news"] = news
        notes = [n for n in (e.get("notes") or []) if isinstance(n, dict) and n.get("n")]
        st["notes"] = notes[:3] if notes else []
        st["live"] = True
    now = datetime.now(timezone.utc)
    data["live"] = True
    data["updated"] = now.isoformat(timespec="seconds")
    data["updated_fa"] = "زنده"
    data["feeds"] = feeds_ok
    data["ai"] = ai_ok
    data["stations"] = [s for s in data["stations"] if s.get("news")]
    return data, feeds_ok, ai_ok


def _refresh():
    try:
        data, feeds_ok, ai_ok = _build()
        with _lock:
            _state.update(data=data, at=time.time(), feeds_ok=feeds_ok, ai=ai_ok)
            if ai_ok or not ai_client.provider():
                _state["error"] = None
    except Exception as e:
        with _lock:
            _state["error"] = str(e)[:300]
            _state["at"] = time.time() - REFRESH_SEC + 120   # retry in 2 minutes
    finally:
        with _lock:
            _state["running"] = False


def get_stations() -> dict:
    """Latest live data (or the snapshot while the first refresh runs). Never blocks on network."""
    with _lock:
        stale = time.time() - _state["at"] > REFRESH_SEC
        if stale and not _state["running"]:
            _state["running"] = True
            threading.Thread(target=_refresh, daemon=True).start()
        data = _state["data"]
    if data is None:
        with open(SNAPSHOT, encoding="utf-8") as f:
            data = json.load(f)
        data["live"] = False
        data["refreshing"] = True
    return data


def status() -> dict:
    with _lock:
        return {"last_refresh": datetime.fromtimestamp(_state["at"], timezone.utc).isoformat(timespec="seconds") if _state["data"] else None,
                "feeds_ok": _state["feeds_ok"], "ai": _state["ai"], "error": _state["error"]}
