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
PER_STATION = 6

# (name, url, kind, fixed station or None)
#   crypto   : crypto newsrooms — every item is relevant
#   official : central banks and regulators — primary sources, routed to their city
#   macro    : financial newsrooms — only items about rates, inflation, stocks, oil, gold, dollar, crypto… are kept
FEEDS = [
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/", "crypto", None),
    ("Cointelegraph", "https://cointelegraph.com/rss", "crypto", None),
    ("Decrypt", "https://decrypt.co/feed", "crypto", None),
    ("The Block", "https://www.theblock.co/rss.xml", "crypto", None),
    ("Bitcoin Magazine", "https://bitcoinmagazine.com/.rss/full/", "crypto", None),
    ("CryptoSlate", "https://cryptoslate.com/feed/", "crypto", None),
    ("Federal Reserve", "https://www.federalreserve.gov/feeds/press_all.xml", "official", "dc"),
    ("Federal Reserve · سخنرانی‌ها", "https://www.federalreserve.gov/feeds/speeches.xml", "official", "dc"),
    ("SEC", "https://www.sec.gov/news/pressreleases.rss", "official", "dc"),
    ("European Central Bank", "https://www.ecb.europa.eu/rss/press.html", "official", "frankfurt"),
    ("Bank of England", "https://www.bankofengland.co.uk/rss/news", "official", "london"),
    ("CNBC", "https://www.cnbc.com/id/100003114/device/rss/rss.html", "macro", None),
    ("CNBC · Economy", "https://www.cnbc.com/id/20910258/device/rss/rss.html", "macro", None),
    ("CNBC · Finance", "https://www.cnbc.com/id/10000664/device/rss/rss.html", "macro", None),
    ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories", "macro", None),
    ("MarketWatch · Markets", "https://feeds.content.dowjones.io/public/rss/mw_marketpulse", "macro", None),
    ("BBC Business", "https://feeds.bbci.co.uk/news/business/rss.xml", "macro", None),
    ("Anadolu Agency", "https://www.aa.com.tr/en/rss/default?cat=economy", "macro", None),
    ("Daily Sabah", "https://www.dailysabah.com/rss/business", "macro", None),
    ("SCMP", "https://www.scmp.com/rss/92/feed", "macro", None),
]
# official feeds publish many routine notices; keep policy, outlook and crypto items only
OFFICIAL_RELEVANT = ["monetary policy", "fomc", "interest rate", "rates", "inflation", "economic outlook", "outlook", "statement",
                     "speech", "testimony", "minutes", "financial stability", "crypto", "digital asset", "stablecoin", "bitcoin",
                     "tokeni", "etf", "payment", "balance sheet", "press conference"]
EXCLUDE = ["enforcement action", "termination of", "civil money penalty", "prohibition order", "application by", "approval of",
           "consent order", "cease and desist", "sentenced", "football", "soccer", "celebrity"]
# a macro/official item is kept only if it is about something that moves markets
RELEVANT = ["crypto", "bitcoin", "btc", "ether", "stablecoin", "digital asset", "token", "blockchain", "etf",
            "fed ", "federal reserve", "fomc", "powell", "interest rate", "rate cut", "rate hike", "rates", "monetary policy",
            "inflation", "cpi", "pce", "jobs report", "payroll", "unemployment", "gdp", "recession", "treasury", "yield", "bond",
            "dollar", "currency", "s&p", "nasdaq", "dow", "stocks", "stock market", "wall street", "equities", "earnings",
            "oil", "crude", "opec", "brent", "gold", "tariff", "trade war", "sanction", "central bank", "ecb", "lagarde",
            "bank of england", "boe", "bailey", "ftse", "pound", "sterling", "lira", "turkey", "turkish", "erdogan", "borsa",
            "bank of japan", "boj", "yen", "pboc", "yuan", "hang seng", "nikkei", "speech", "statement", "testimony"]
UA = {"User-Agent": "Mozilla/5.0 (compatible; CryptoAI-Radio/1.0)"}

# First match wins: specific places before topic-based desks.
RULES = [
    ("istanbul", ["turkey", "turkish", "türkiye", "turkiye", "istanbul", "ankara", "lira", "erdogan", "erdoğan", "borsa istanbul", "bist"]),
    ("sansalvador", ["el salvador", "bukele", "salvadoran"]),
    ("nairobi", ["kenya", "nairobi", "east africa"]),
    ("lagos", ["nigeria", "lagos", "ghana", "south africa", "africa"]),
    ("seoul", ["korea", "upbit", "bithumb", "seoul"]),
    ("tokyo", ["japan", "tokyo", "metaplanet", "yen ", "bank of japan", "boj", "nikkei"]),
    ("hk", ["hong kong", "hkma", "china", "chinese", "beijing", "yuan", "pboc", "hang seng", "shanghai"]),
    ("mumbai", ["india", "mumbai", "wazirx", "coindcx", "rupee"]),
    ("dubai", ["dubai", "uae", "abu dhabi", "emirates", "saudi", "middle east", "bahrain", "qatar", "vara", "opec", "crude", "oil price", "brent", "iran"]),
    ("london", ["u.k.", " uk ", "uk's", "britain", "british", "fca", "london", "bank of england", "boe", "bailey", "ftse", "sterling", "pound"]),
    ("frankfurt", ["ecb", "european central bank", "lagarde", "eurozone", "euro zone", "euro area", "bund", "dax", "frankfurt", "bundesbank"]),
    ("paris", ["mica", "european", "europe", " eu ", "eu's", "ecb", "france", "french", "germany", "german", "digital euro", "italy", "spain"]),
    ("saopaulo", ["brazil", "argentina", "latin america", "latam", "mexico", "colombia", "milei"]),
    ("dc", [" sec ", "sec's", "securities and exchange", "federal reserve", " fed ", "fed's", "powell", "congress", "senate",
            "white house", "trump", "treasury", "cftc", "clarity act", "genius act", "midterm", "washington", "lawmakers", "irs",
            "fomc", "rate cut", "rate hike", "interest rate", "inflation", "cpi", "pce", "jobs report", "payroll", "unemployment", "tariff"]),
    ("zug", ["ethereum", "vitalik", " ether ", " eth ", "glamsterdam", "layer-2", "layer 2", "switzerland", "swiss"]),
    ("nyc", ["etf", "blackrock", "ibit", "fidelity", "nasdaq", "wall street", "s&p", "coinbase", "microstrategy", "strategy",
             "jpmorgan", "goldman", "nyse", "new york", "liquidat", "dow", "stocks", "stock market", "equities", "earnings",
             "nvidia", "gold", "oil", "bitcoin", "btc", "price", "market"]),
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


def _when(s):
    if not s:
        return None
    try:
        return parsedate_to_datetime(s).astimezone(timezone.utc).timestamp()
    except Exception:
        pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc).timestamp()
    except Exception:
        return None


def _fetch_feed(feed):
    name, url, kind, fixed = feed
    try:
        r = requests.get(url, headers=UA, timeout=12)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        out = []
        atom = "{http://www.w3.org/2005/Atom}"
        dc = "{http://purl.org/dc/elements/1.1/}"
        nodes = list(root.iter("item")) or list(root.iter(atom + "entry"))
        for it in nodes:
            title = _clean(_text(it, "title") or _text(it, atom + "title"), 220)
            link = _text(it, "link")
            if not link:
                l = it.find(atom + "link")
                link = l.get("href", "") if l is not None else ""
            ts = _when(_text(it, "pubDate") or _text(it, dc + "date") or _text(it, atom + "updated") or _text(it, atom + "published"))
            if not title or not link or not ts:
                continue
            desc = _clean(_text(it, "description") or _text(it, atom + "summary") or _text(it, atom + "content"), 300)
            if kind != "crypto":
                hay = " " + (title + " " + desc).lower() + " "
                words = OFFICIAL_RELEVANT if kind == "official" else RELEVANT
                if not any(w in hay for w in words) or any(w in hay for w in EXCLUDE):
                    continue
            out.append({"title": title, "desc": desc, "url": link, "ts": ts, "source": name, "kind": kind, "fixed": fixed})
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


_tr_cache: dict = {}      # url -> {"t": fa title, "b": fa summary}   (each headline is translated once)
_notes_cache: dict = {}   # station id -> {"key": urls, "notes": [...], "at": time}
NOTES_MIN_AGE = 1800      # re-analyse a station at most every 30 min unless its headlines changed


def _gtranslate(text: str) -> str:
    """Google Translate (public web endpoint, no key). Used only when the AI translation fails."""
    if not text:
        return ""
    try:
        r = requests.get("https://translate.googleapis.com/translate_a/single",
                         params={"client": "gtx", "sl": "auto", "tl": "fa", "dt": "t", "q": text[:1500]}, headers=UA, timeout=10)
        r.raise_for_status()
        return "".join(seg[0] for seg in r.json()[0] if seg and seg[0]).strip()
    except Exception:
        return ""


ASSETS = [("BTC", "بیت‌کوین"), ("ETH", "اتریوم"), ("ALT", "آلت‌کوین‌ها"), ("GOLD", "طلا"),
          ("OIL", "نفت"), ("SPX", "S&P 500"), ("DXY", "دلار آمریکا")]
ASSET_KEYS = {k for k, _ in ASSETS}

# Fallback analysis when the AI is unavailable: well-known cross-market links, written in Persian.
_HEUR = [
    (r"rate cut|cuts rates|cut interest rates|dovish|lower(s|ed)? (interest )?rates|lower the target range|reduce the target range|easing", 3,
     [("BTC", 1, 2), ("ETH", 1, 2), ("ALT", 1, 2), ("GOLD", 1, 2), ("SPX", 1, 2), ("DXY", -1, 2)],
     "کاهش نرخ بهره یعنی پول ارزان‌تر و میل بیشتر به دارایی‌های پرریسک"),
    (r"rate hike|raises rates|raise interest rates|raise the target range|hawkish|higher for longer", 3,
     [("BTC", -1, 2), ("ETH", -1, 2), ("ALT", -1, 2), ("SPX", -1, 2), ("GOLD", -1, 1), ("DXY", 1, 2)],
     "نرخ بهرهٔ بالاتر پول را گران می‌کند و به دارایی‌های پرریسک فشار می‌آورد"),
    (r"inflation (rises|rose|jumps|accelerat|hotter|higher)|cpi (rises|rose|beats|hotter|jumps)|prices rise faster", 3,
     [("BTC", -1, 1), ("SPX", -1, 1), ("GOLD", 1, 1), ("DXY", 1, 1)],
     "تورم بالاتر احتمال کاهش نرخ بهره را کم می‌کند"),
    (r"inflation (cools|eases|slows|falls)|cpi (cools|eases|falls|slows)", 3,
     [("BTC", 1, 1), ("SPX", 1, 1), ("DXY", -1, 1)],
     "تورم آرام‌تر راه کاهش نرخ بهره را باز می‌کند"),
    (r"etf.{0,60}(inflow|inflows|draws|attracts)", 2, [("BTC", 1, 2)], "ورود پول به ETFها یعنی تقاضای نهادی بیشتر"),
    (r"etf.{0,60}(outflow|outflows|withdrawals|bleed)", 2, [("BTC", -1, 2)], "خروج پول از ETFها یعنی تقاضای نهادی کمتر"),
    (r"hack|exploit|stolen|drained|breach", 2, [("ALT", -1, 2), ("BTC", -1, 1)], "هک اعتماد بازار را کم می‌کند و فروش را بیشتر"),
    (r"sell-?off|stocks (fall|slide|tumble|drop|sink)|(s&p 500|s&p|nasdaq|dow) (falls|drops|slides|tumbles|sinks)|worst day", 2,
     [("SPX", -1, 2), ("BTC", -1, 1), ("ETH", -1, 1), ("ALT", -1, 2), ("GOLD", 1, 1)],
     "ریزش سهام یعنی فرار از ریسک؛ کریپتو معمولاً همراه سهام پایین می‌آید"),
    (r"stocks (rise|rally|gain|climb|jump|hit record)|(s&p 500|s&p|nasdaq|dow) (rises|rallies|gains|climbs|hits (a )?record)", 2,
     [("SPX", 1, 2), ("BTC", 1, 1), ("ALT", 1, 1)],
     "رشد سهام یعنی میل به ریسک؛ معمولاً به کریپتو هم کمک می‌کند"),
    (r"oil (prices )?(jump|jumps|surge|surges|rise|rises|climb|climbs|spike|spikes)|opec.{0,40}(cut|reduce)|crude (jumps|surges|rises)", 2,
     [("OIL", 1, 2), ("BTC", -1, 1), ("SPX", -1, 1)],
     "نفت گران‌تر تورم را بالا می‌برد و کاهش نرخ بهره را عقب می‌اندازد"),
    (r"oil (prices )?(fall|falls|drop|drops|slide|slides|plunge|plunges|slump)|crude (falls|drops|slides)", 2,
     [("OIL", -1, 2), ("BTC", 1, 1)], "نفت ارزان‌تر فشار تورمی را کم می‌کند"),
    (r"gold (hits|record|rises|surges|jumps|climbs|rallies)", 2, [("GOLD", 1, 2)], "تقاضا برای دارایی امن بالا رفته"),
    (r"gold (falls|drops|slides|slumps)", 2, [("GOLD", -1, 2)], "تقاضای دارایی امن کم شده"),
    (r"dollar (strengthens|rises|jumps|surges|gains)|yields? (rise|rises|jump|jumps|climb|surge)", 2,
     [("DXY", 1, 2), ("BTC", -1, 1), ("GOLD", -1, 1)], "دلار قوی‌تر یا بازده بالاتر اوراق، جذابیت کریپتو و طلا را کم می‌کند"),
    (r"dollar (weakens|falls|slides|drops)|yields? (fall|falls|drop|drops|slide)", 2,
     [("DXY", -1, 2), ("BTC", 1, 1), ("GOLD", 1, 1)], "دلار ضعیف‌تر معمولاً به کریپتو و طلا کمک می‌کند"),
    (r"lira (hits record low|plunges|falls|slumps|weakens)", 1, [("BTC", 1, 1)], "ضعف لیر تقاضای محلی برای بیت‌کوین و استیبل‌کوین را بالا می‌برد"),
    (r"approv.{0,40}(etf|stablecoin)|bill passes|regulatory clarity|green light", 2,
     [("BTC", 1, 1), ("ALT", 1, 2)], "شفافیت قانونی راه ورود سرمایهٔ بیشتر را باز می‌کند"),
    (r"(lawsuit|sues|crackdown|ban(s|ned)?|charges).{0,60}(crypto|exchange|token)", 2,
     [("ALT", -1, 2), ("BTC", -1, 1)], "فشار قانونی ریسک بازار را بالا می‌برد"),
    (r"liquidat", 2, [("BTC", -1, 1), ("ALT", -1, 1)], "لیکوئید شدن معامله‌گران اهرمی، نوسان را تشدید می‌کند"),
    (r"tariff|trade war", 2, [("SPX", -1, 1), ("BTC", -1, 1), ("GOLD", 1, 1)], "جنگ تجاری ریسک رشد اقتصادی را بالا می‌برد"),
]


def _heuristic(title: str, desc: str, kind: str):
    hay = (title + " " + desc).lower()
    imp, out = (2 if kind == "official" else 1), {}
    for pat, i, effects, why in _HEUR:
        if re.search(pat, hay):
            imp = max(imp, i)
            for a, d, st in effects:
                if a not in out:
                    out[a] = {"a": a, "d": d, "s": st, "w": why}
    if "ether" in hay or " eth " in f" {hay} " or "ethereum" in hay:
        for k, v in list(out.items()):
            if k == "BTC" and "ETH" not in out:
                out["ETH"] = dict(v, a="ETH")
    return imp, list(out.values())


def _clean_impacts(lst):
    out = []
    for x in lst or []:
        if not isinstance(x, dict):
            continue
        a = str(x.get("a", "")).upper()
        if a not in ASSET_KEYS:
            continue
        try:
            d = max(-1, min(1, int(x.get("d", 0))))
            s_ = max(1, min(3, int(x.get("s", 1))))
        except Exception:
            continue
        out.append({"a": a, "d": d, "s": s_, "w": str(x.get("w") or "")[:160]})
    return out[:6]


def _translate(items):
    """For every new headline: Persian title + summary, importance and its effect on BTC/ETH/alts/gold/oil/S&P/dollar.
    Small batches so no answer is cut off; each headline is analysed once."""
    todo = [it for it in items if it["url"] not in _tr_cache]
    for k in range(0, len(todo), 6):
        batch = todo[k:k + 6]
        payload = [{"i": j, "title": it["title"], "desc": it["desc"][:240], "type": it.get("kind", "crypto")} for j, it in enumerate(batch)]
        prompt = (
            "You are a senior cross-market analyst writing for a Persian crypto & markets website.\n"
            "For each news item return:\n"
            "  t: fluent Persian (Farsi) title, max 14 words\n"
            "  b: Persian summary, 1-2 sentences, ONLY from the given text\n"
            "  imp: market importance 1 (minor), 2 (notable), 3 (market-moving)\n"
            "  im: list of assets this news can move, from exactly these keys: BTC, ETH, ALT (altcoins), GOLD, OIL, SPX (S&P 500), DXY (US dollar).\n"
            "      each: {a: key, d: 1 up / -1 down / 0 unclear, s: 1 weak / 2 moderate / 3 strong, w: Persian, max 14 words, the channel of effect}\n"
            "      Include only assets with a real, explainable link (e.g. stocks down -> risk-off -> BTC down; oil up -> inflation -> later rate cuts -> crypto pressure;\n"
            "      stronger dollar / higher yields -> pressure on crypto and gold; ETF inflows -> BTC up; hacks -> alts down). Empty list if none.\n"
            "Keep tickers, company and person names in Latin letters where Persian readers expect them. No buy/sell advice, no price targets.\n"
            'Return ONLY JSON: {"items": [{"i": 0, "t": "...", "b": "...", "imp": 2, "im": [{"a": "BTC", "d": -1, "s": 2, "w": "..."}]}]}\n'
            "ITEMS: " + json.dumps(payload, ensure_ascii=False))
        try:
            raw = ai_client.ask(prompt, json_mode=True, max_tokens=3500, timeout=90)
            m = re.search(r"\{[\s\S]*\}", raw)
            got = json.loads(m.group(0) if m else raw).get("items", [])
            for x in got:
                j = x.get("i")
                if isinstance(j, int) and 0 <= j < len(batch) and x.get("t"):
                    it = batch[j]
                    try:
                        imp = max(1, min(3, int(x.get("imp", 1))))
                    except Exception:
                        imp = 1
                    ims = _clean_impacts(x.get("im"))
                    if not ims:
                        imp2, ims = _heuristic(it["title"], it["desc"], it.get("kind", "crypto"))
                        imp = max(imp, imp2)
                    _tr_cache[it["url"]] = {"t": str(x["t"]).strip(), "b": str(x.get("b") or "").strip(), "imp": imp, "im": ims, "by": "ai"}
        except Exception as e:
            _state["error"] = f"AI translate: {str(e)[:160]}"
    # anything the AI could not handle: Google Translate + rule-based impact, so nothing stays English or unanalysed
    for it in todo:
        if it["url"] in _tr_cache:
            continue
        t, b = _gtranslate(it["title"]), _gtranslate(it["desc"]) if it["desc"] else ""
        imp, ims = _heuristic(it["title"], it["desc"], it.get("kind", "crypto"))
        if t:
            _tr_cache[it["url"]] = {"t": t, "b": b or "", "imp": imp, "im": ims, "by": "auto"}
    if len(_tr_cache) > 3000:
        for key in list(_tr_cache)[:1000]:
            _tr_cache.pop(key, None)


# ---------------------------------------------------------------- market brief (asset pressure from news)
_brief_ai = {"key": None, "text": {}, "at": 0.0}


def _brief(items, stations_by_url):
    now = time.time()
    agg = {k: {"sum": 0.0, "drivers": []} for k in ASSET_KEYS}
    feed = []
    for it in items:
        tr = _tr_cache.get(it["url"])
        if not tr:
            continue
        age_h = max(0.0, (now - it["ts"]) / 3600)
        entry = {"t": tr["t"], "b": tr["b"], "ts": it["ts"], "imp": tr.get("imp", 1), "im": tr.get("im", []),
                 "kind": it.get("kind", "crypto"), "source": {"name": it["source"], "url": it["url"]},
                 "city": stations_by_url.get(it["url"], "")}
        feed.append(entry)
        if age_h > 24:
            continue
        for x in tr.get("im", []):
            wgt = tr.get("imp", 1) * x["s"] * (0.5 ** (age_h / 8))   # newer and bigger news weigh more
            agg[x["a"]]["sum"] += x["d"] * wgt
            if x["d"]:
                agg[x["a"]]["drivers"].append({"t": tr["t"], "w": x["w"], "d": x["d"], "s": x["s"], "ts": it["ts"],
                                               "url": it["url"], "source": it["source"], "_w": abs(wgt)})
    assets = []
    for key, name in ASSETS:
        a = agg[key]
        import math
        score = round(100 * math.tanh(a["sum"] / 6))
        label = ("صعودی قوی" if score >= 45 else "صعودی" if score >= 12 else
                 "نزولی قوی" if score <= -45 else "نزولی" if score <= -12 else "خنثی")
        drivers = sorted(a["drivers"], key=lambda x: -x["_w"])[:4]
        for d in drivers:
            d.pop("_w", None)
        assets.append({"key": key, "name": name, "score": score, "label": label, "drivers": drivers, "count": len(a["drivers"])})
    feed.sort(key=lambda x: (-(x["ts"] // 3600), -x["imp"], -x["ts"]))
    return assets, feed[:40]


def _brief_summaries(assets, market_hint):
    """One AI call (at most every 30 min, or when the drivers change): a short Persian 'why' per asset."""
    key = "|".join(f"{a['key']}:{a['score']}:" + ",".join(d["url"] for d in a["drivers"]) for a in assets)
    if _brief_ai["key"] == key or (time.time() - _brief_ai["at"] < 1800 and _brief_ai["text"]):
        return _brief_ai["text"]
    if not ai_client.provider():
        return {}
    payload = {a["key"]: {"name": a["name"], "news_pressure": a["label"],
                          "drivers": [{"news": d["t"], "effect": "up" if d["d"] > 0 else "down", "why": d["w"]} for d in a["drivers"]]}
               for a in assets}
    prompt = (
        "You write the daily 'what is moving the market' brief of a Persian crypto & markets website.\n"
        "For each asset, write 2 short Persian sentences (max 40 words total) explaining what today's news means for it, "
        "naming the main driver and the channel of effect. If there are no drivers, say the news flow is quiet for it. "
        "No buy/sell advice, no price targets.\n"
        f"Live market numbers: {market_hint}\n"
        'Return ONLY JSON: {"BTC": "...", "ETH": "...", "ALT": "...", "GOLD": "...", "OIL": "...", "SPX": "...", "DXY": "..."}\n'
        "DATA: " + json.dumps(payload, ensure_ascii=False))
    try:
        raw = ai_client.ask(prompt, json_mode=True, max_tokens=1500, timeout=90)
        m = re.search(r"\{[\s\S]*\}", raw)
        got = json.loads(m.group(0) if m else raw)
        text = {k: str(v)[:400] for k, v in got.items() if k in ASSET_KEYS and v}
        if text:
            _brief_ai.update(key=key, text=text, at=time.time())
    except Exception as e:
        _state["error"] = f"AI brief: {str(e)[:160]}"
    return _brief_ai["text"]


def _station_notes(by_station: dict, market_hint: str):
    """Up/down notes per station, only for stations whose headlines changed (or older than 30 min)."""
    now = time.time()
    need = {}
    for sid, items in by_station.items():
        if not items:
            continue
        key = "|".join(it["url"] for it in items)
        c = _notes_cache.get(sid)
        if c and (c["key"] == key or now - c["at"] < NOTES_MIN_AGE):
            continue
        need[sid] = items
    sids = list(need)
    for k in range(0, len(sids), 4):
        part = {sid: [{"title": it["title"], "desc": it["desc"][:160]} for it in need[sid]] for sid in sids[k:k + 4]}
        prompt = (
            "You are a senior cross-market analyst for a Persian crypto radio. For each station id, read its headlines and write up to 3 notes "
            "on what could move and in which direction: crypto (BTC, ETH, alts, stablecoins) and, where relevant, S&P 500/Nasdaq, gold, oil, the dollar.\n"
            "In each note name the channel of effect in plain Persian, for example: stocks falling -> risk-off -> BTC usually follows down; "
            "stronger dollar or higher Treasury yields -> pressure on crypto; oil up -> inflation -> later Fed cuts -> pressure; "
            "rate cuts / weaker dollar -> supportive; weak local currency (e.g. Turkish lira) -> more local demand for stablecoins and BTC. "
            "Use the live market numbers below when they help. Say 'mixed' when the effect is unclear.\n"
            'Return ONLY JSON: {"<station id>": [{"c": ["BTC"], "dir": "up"|"down"|"mixed", "n": "Persian, max 25 words", "w": "Persian reason or timing, max 12 words"}]}\n'
            "Rules: use only the given headlines; no buy/sell advice, no targets, no entry points; if no real market effect use \"mixed\".\n"
            f"Market context: {market_hint}\nDATA: " + json.dumps(part, ensure_ascii=False))
        try:
            raw = ai_client.ask(prompt, json_mode=True, max_tokens=2000, timeout=90)
            m = re.search(r"\{[\s\S]*\}", raw)
            got = json.loads(m.group(0) if m else raw)
            for sid in part:
                notes = [n for n in (got.get(sid) or []) if isinstance(n, dict) and n.get("n")][:3]
                if notes:
                    _notes_cache[sid] = {"key": "|".join(it["url"] for it in need[sid]), "notes": notes, "at": now}
        except Exception as e:
            _state["error"] = f"AI notes: {str(e)[:160]}"


def _market_hint():
    try:
        import trader_engine
        parts = []
        for s in ("BTC", "ETH"):
            rows, src = trader_engine.fetch_rows(s, "1h", 25)
            parts.append(f"{s} {rows[-1][4]:,.2f} USD ({(rows[-1][4] / rows[0][4] - 1) * 100:+.2f}% 24h, {src})")
        try:
            import markets
            extra = markets.hint()
            if extra:
                parts.append(extra)
        except Exception:
            pass
        return "; ".join(parts)
    except Exception:
        return "unknown"


def _build():
    with open(SNAPSHOT, encoding="utf-8") as f:
        snap = json.load(f)
    with ThreadPoolExecutor(max_workers=10) as ex:
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
        sid = it.get("fixed") or classify(it["title"], it["desc"])
        if sid in by_station and len(by_station[sid]) < PER_STATION:
            by_station[sid].append(it)

    ai_ok = False
    _state["error"] = None
    recent = [it for it in items if time.time() - it["ts"] < 36 * 3600][:60]
    on_air = [it for lst in by_station.values() for it in lst]
    _translate(list({it["url"]: it for it in recent + on_air}.values()))
    hint = _market_hint()
    if ai_client.provider():
        _station_notes(by_station, hint)
    ai_ok = bool(ai_client.provider()) and _state["error"] is None
    city = {}
    for sid, lst in by_station.items():
        name = next((x["fa"] for x in snap["stations"] if x["id"] == sid), "")
        for it in lst:
            city[it["url"]] = name
    for it in recent:
        if it["url"] not in city:
            sid = it.get("fixed") or classify(it["title"], it["desc"])
            city[it["url"]] = next((x["fa"] for x in snap["stations"] if x["id"] == sid), "")
    assets, feed = _brief(recent, city)
    summaries = _brief_summaries(assets, hint)
    for a in assets:
        a["summary"] = summaries.get(a["key"], "")

    data = copy.deepcopy(snap)
    for st in data["stations"]:
        live = by_station.get(st["id"]) or []
        if not live:
            st["live"] = False
            continue
        news = []
        for it in live:
            fa = _tr_cache.get(it["url"]) or {}
            news.append({
                "d": datetime.fromtimestamp(it["ts"], timezone.utc).strftime("%d %b %H:%M UTC"),
                "ts": it["ts"],
                "t": fa.get("t") or it["title"],
                "b": fa.get("b") or it["desc"],
                "en": it["title"] + ". " + it["desc"],
                "lang": "fa" if fa.get("t") else "en",
                "kind": it.get("kind", "crypto"),
                "imp": fa.get("imp", 1),
                "im": fa.get("im", []),
                "source": {"name": it["source"], "url": it["url"]},
            })
        st["news"] = news
        st["notes"] = (_notes_cache.get(st["id"]) or {}).get("notes", [])
        st["live"] = True
    now = datetime.now(timezone.utc)
    data["live"] = True
    data["updated"] = now.isoformat(timespec="seconds")
    data["updated_fa"] = "زنده"
    data["feeds"] = feeds_ok
    data["ai"] = ai_ok
    data["stations"] = [s for s in data["stations"] if s.get("news")]
    data["brief"] = {"updated": data["updated"], "assets": assets, "feed": feed}
    return data, feeds_ok, ai_ok


def _refresh():
    try:
        data, feeds_ok, ai_ok = _build()
        with _lock:
            _state.update(data=data, at=time.time(), feeds_ok=feeds_ok, ai=ai_ok)
            untranslated = any(n.get("lang") == "en" for st in data["stations"] for n in st.get("news", []))
            if untranslated and ai_client.provider():
                _state["at"] = time.time() - REFRESH_SEC + 120   # try the missing translations again in 2 minutes
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


def get_brief() -> dict:
    data = get_stations()
    b = data.get("brief")
    if not b:
        return {"updated": None, "assets": [], "feed": [], "warming_up": True}
    return b


def status() -> dict:
    with _lock:
        return {"last_refresh": datetime.fromtimestamp(_state["at"], timezone.utc).isoformat(timespec="seconds") if _state["data"] else None,
                "feeds_ok": _state["feeds_ok"], "ai": _state["ai"], "error": _state["error"]}
