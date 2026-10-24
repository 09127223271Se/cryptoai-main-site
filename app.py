"""
CryptoAI Main Site — یک سایت واحد
عمومی: کره رادیو + تریدر + تحلیل کریپتو
فقط مدیر (/admin): پیدا کردن مشتری + پنل ایجنت تلگرام
"""

import hmac
import os
import secrets
import sys
import threading
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, Response, jsonify, redirect, render_template, request, session, url_for

import ai_client
import markets
import news_live
import pro
import telegram_bot
import trader_engine
import tts

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BUSINESS_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "crypto-business"))
if os.path.isdir(BUSINESS_PATH):
    sys.path.insert(0, BUSINESS_PATH)

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  SESSION_COOKIE_SECURE=bool(os.environ.get("RENDER")), PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 14)
if trader_engine.trader_bp is not None:
    app.register_blueprint(trader_engine.trader_bp)      # /api/trader/scan, /api/trader/setup/<coin>

PAGES = {"search": "/search", "home": "/", "pro": "/pro", "radio": "/radio", "trader": "/trader", "analysis": "/analysis", "sales": "/sales", "admin": "/admin"}
PAGES_EN = {"search": "/en/search", "home": "/en", "pro": "/en/pro", "radio": "/en/radio", "trader": "/en/trader", "analysis": "/en/analysis",
            "sales": "/sales", "admin": "/admin"}
PUBLIC = ("home", "pro", "radio", "trader", "analysis", "search")


# ---------- admin login (password lives only in Render: ADMIN_PASSWORD) ----------
def is_admin() -> bool:
    return bool(session.get("admin"))


def admin_required(api=False):
    def deco(fn):
        @wraps(fn)
        def inner(*a, **kw):
            if is_admin():
                return fn(*a, **kw)
            if api:
                return jsonify({"ok": False, "error": "فقط مدیر سایت"}), 401
            return redirect(url_for("admin_page", next=request.path))
        return inner
    return deco


def channel_url(lang: str = "fa") -> str:
    """Public Telegram channel link for the 'join' buttons (PUBLIC_CHANNEL_URL[_EN], or derived from @channel)."""
    url = os.environ.get("PUBLIC_CHANNEL_URL_EN" if lang == "en" else "PUBLIC_CHANNEL_URL", "").strip()
    if url:
        return url
    ch = os.environ.get("TELEGRAM_CHANNEL_EN" if lang == "en" else "TELEGRAM_CHANNEL_ID", "").strip()
    return f"https://t.me/{ch[1:]}" if ch.startswith("@") else ""


def socials() -> list:
    """Social profile links for the footer (set in Render; Instagram has a default)."""
    out = []
    for key, label, default in (("INSTAGRAM_URL", "Instagram", "https://www.instagram.com/cryptoglobalfarsi/"),
                                ("TIKTOK_URL", "TikTok", ""), ("X_URL", "X", "")):
        url = os.environ.get(key, default).strip()
        if url:
            out.append((label, url))
    return out


def page(name: str, template: str, lang: str = "fa", **extra):
    """Render a page in server mode (links to Flask routes, AI through /api/ai). lang='en' uses templates/en/."""
    pages = PAGES_EN if lang == "en" else PAGES
    alt = (PAGES if lang == "en" else PAGES_EN)[name] if name in PUBLIC else None
    return render_template(
        ("en/" + template) if lang == "en" else template, page=name, mode="server", api_base="", lang=lang,
        is_admin=is_admin(), channel=channel_url(lang), alt_url=alt, socials=socials(),
        asset=lambda p: url_for("static", filename=p) if p else "/static/",
        link=lambda n: pages[n], **extra,
    )


# ---------- Telegram agent: start once per process ----------
_boot = {"done": False}


@app.before_request
def _boot_agent():
    if not _boot["done"]:
        _boot["done"] = True
        news_live.get_stations()                     # start the first news refresh
        threading.Thread(target=telegram_bot.ensure_webhook, daemon=True).start()
        telegram_bot.start_loop()


# ---------- Pages ----------
@app.route("/")
def home():
    return page("home", "brief.html")


@app.route("/pro")
def pro_page():
    st = pro.stats()
    return page("pro", "pro.html", pro_ready=st["ready"], usdt_on=st["ready"] and st["usdt_wallet"],
                price_usdt=st["price_usdt"], price_stars=st["price_stars"])


@app.route("/pro/stars")
def pro_stars():
    link = pro.stars_link()
    return redirect(link) if link else redirect("/pro?unavailable=1")


@app.route("/api/pro/order", methods=["POST"])
def api_pro_order():
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0]
    q = _ai_hits["order:" + ip]
    while q and time.time() - q[0] > 3600:
        q.popleft()
    if len(q) >= 10:
        return jsonify({"ok": False, "error": "تعداد درخواست زیاد است؛ کمی بعد دوباره امتحان کنید."}), 429
    q.append(time.time())
    try:
        return jsonify({"ok": True, **pro.new_order()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:200]}), 503


@app.route("/api/pro/order/<oid>")
def api_pro_order_status(oid):
    return jsonify(pro.check_order(oid))


@app.route("/api/pro/brief", methods=["POST"])
@admin_required(api=True)
def api_pro_brief():
    return jsonify({"ok": pro.morning_brief(force=True)})


@app.route("/radio")
def radio_page():
    return page("radio", "index.html")


@app.route("/trader")
def trader_page():
    return page("trader", "trader.html")


@app.route("/analysis")
def analysis_page():
    return page("analysis", "analysis.html")


# ---------- Search: coins and news ----------
@app.route("/search")
def search_page():
    return page("search", "search.html", q=request.args.get("q", "")[:60])


@app.route("/en/search")
def search_en():
    return page("search", "search.html", "en", q=request.args.get("q", "")[:60])


def _news_pool():
    """Every analysed story we have: the brief feed plus the radio stations, newest first, no duplicates."""
    data = news_live.get_stations()
    feed = list((data.get("brief") or {}).get("feed") or [])
    seen = {n["source"]["url"] for n in feed}
    for st in data.get("stations", []):
        for n in st.get("news", []):
            if n.get("source", {}).get("url") in seen or not n.get("ts"):
                continue
            seen.add(n["source"]["url"])
            feed.append({"t": n.get("t"), "b": n.get("b"), "en_t": n.get("en_t") or n.get("en", ""), "en_b": n.get("en_b", ""),
                         "ts": n["ts"], "imp": n.get("imp", 1), "im": n.get("im", []), "kind": n.get("kind", "crypto"),
                         "source": n["source"], "city": st.get("fa", ""), "city_en": st.get("en", "")})
    feed.sort(key=lambda x: -(x.get("ts") or 0))
    return feed


@app.route("/api/search")
def api_search():
    import coins
    q = request.args.get("q", "").strip()[:60]
    if not q:
        return jsonify({"q": q, "coin": None, "suggest": [], "news": []})
    if request.args.get("s"):           # typing suggestions only
        return jsonify({"q": q, "suggest": coins.suggest(q)})
    sym = coins.find(q)
    coin = None
    if sym:
        en, fa = coins.names(sym)
        coin = {"sym": sym, "en": en, "fa": fa}
    ql = q.lower()
    words = {ql}
    if sym:
        en, fa = coins.names(sym)
        words |= {sym.lower(), en.lower(), fa, fa.replace("\u200c", "")}
    asset = {"BTC": "BTC", "ETH": "ETH", "PAXG": "GOLD"}.get(sym or "", None)
    out = []
    for n in _news_pool():
        hay = " ".join(str(n.get(k) or "") for k in ("t", "b", "en_t", "en_b")).lower()
        hit = any((f" {w} " in f" {hay} ") if (w.isascii() and len(w) <= 4) else (w in hay) for w in words if w)
        if not hit and asset:
            hit = any(x.get("a") == asset and x.get("d") for x in n.get("im") or [])
        if hit:
            out.append(n)
        if len(out) >= 20:
            break
    return jsonify({"q": q, "coin": coin, "suggest": coins.suggest(q), "news": out})


@app.route("/api/coin/<sym>")
def api_coin(sym):
    """Live chart analysis for any coin: price, trend, support/resistance, 24h probable range. No entry points."""
    import coins
    import post_card
    sym = (coins.find(sym) or "").upper()
    if not sym:
        return jsonify({"ok": False, "error": "bad symbol"}), 400
    en, fa = coins.names(sym)
    if sym in ("USDT", "USDC", "DAI", "FDUSD"):
        return jsonify({"ok": True, "stable": True, "sym": sym, "en": en, "fa": fa, "price": 1.0})
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0]
    hits = _ai_hits["coin:" + ip]
    while hits and time.time() - hits[0] > 3600:
        hits.popleft()
    if len(hits) >= 120:
        return jsonify({"ok": False, "error": "rate_limited"}), 429
    hits.append(time.time())
    scores = {a["key"]: a["score"] for a in (news_live.get_brief().get("assets") or [])}
    key = sym if sym in ("BTC", "ETH") else "GOLD" if sym == "PAXG" else "ALT"
    try:
        ms = post_card.market_state(sym, scores.get(key, 0))
    except Exception:
        ms = None
    if not ms:
        return jsonify({"ok": False, "error": "not_found", "sym": sym}), 404
    return jsonify({"ok": True, "sym": sym, "en": en, "fa": fa, "news_key": key, "news_score": scores.get(key, 0),
                    "price": ms["price"], "ch24": ms["ch24"], "res": ms["res"], "sup": ms["sup"],
                    "week_high": ms["week_high"], "week_low": ms["week_low"], "rsi": ms["rsi"], "trend": ms["trend"],
                    "tags": ms["tags"], "tags_en": [post_card.TAG_EN.get(t, t) for t in ms["tags"]],
                    "verdict": ms["verdict"], "verdict_fa": post_card.VERDICT_FA[ms["verdict"]],
                    "verdict_en": post_card.VERDICT_EN[ms["verdict"]],
                    "p05": ms["p05"], "p25": ms["p25"], "p50": ms["p50"], "p75": ms["p75"], "p95": ms["p95"],
                    "touch_res": ms["touch_res"], "touch_sup": ms["touch_sup"],
                    "candles": [[int(t), o, h, l, c] for t, o, h, l, c in ms["candles"]]})


# ---------- English site ----------
@app.route("/en")
@app.route("/en/")
def home_en():
    return page("home", "brief.html", "en")


@app.route("/en/radio")
def radio_en():
    return page("radio", "index.html", "en")


@app.route("/en/trader")
def trader_en():
    return page("trader", "trader.html", "en")


@app.route("/en/analysis")
def analysis_en():
    return page("analysis", "analysis.html", "en")


@app.route("/en/pro")
def pro_en():
    st = pro.stats()
    return page("pro", "pro.html", "en", pro_ready=st["ready"], usdt_on=st["ready"] and st["usdt_wallet"],
                price_usdt=st["price_usdt"], price_stars=st["price_stars"])


@app.route("/sales")
@admin_required()
def sales_page():
    return page("sales", "sales.html")


_login_fails = defaultdict(deque)


@app.route("/admin", methods=["GET", "POST"])
def admin_page():
    error = None
    if request.method == "POST":
        ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0]
        q = _login_fails[ip]
        while q and time.time() - q[0] > 900:
            q.popleft()
        pw = os.environ.get("ADMIN_PASSWORD", "")
        if len(q) >= 8:
            error = "تلاش زیاد؛ ۱۵ دقیقه بعد دوباره امتحان کنید."
        elif not pw:
            error = "رمز مدیر روی سرور تنظیم نشده (ADMIN_PASSWORD در Render)."
        elif hmac.compare_digest(request.form.get("password", ""), pw):
            session.permanent = True
            session["admin"] = True
            nxt = request.args.get("next", "/admin")
            return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else "/admin")
        else:
            q.append(time.time())
            error = "رمز درست نیست."
    if not is_admin():
        return page("admin", "login.html", error=error)
    import growth
    return page("admin", "admin.html", bot=telegram_bot.status(), cfg=telegram_bot.cfg(), prostat=pro.stats(), grow=growth.stats())


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# ---------- Health & AI ----------
def _card_fa():
    try:
        import post_card
        return post_card.FA
    except Exception:
        return False


@app.route("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "time": datetime.now(timezone.utc).isoformat(),
        "business_module": os.path.isdir(BUSINESS_PATH),
        "ai_provider": ai_client.provider(),
        "telegram": telegram_bot.ready(),
        "pro": {k: v for k, v in pro.stats().items() if k in ("ready", "usdt_wallet", "stars_link", "last_error")},
        "tts": tts.available(),
        "post_card_persian": _card_fa(),
        "market_data_errors": dict(list(trader_engine.last_errors.items())[:5]),
        "news": news_live.status(),
    })


@app.route("/api/ai/status")
def ai_status():
    p = ai_client.provider()
    return jsonify({"ok": p is not None, "provider": p, "images": False})


_ai_hits = defaultdict(deque)
AI_PER_HOUR = int(os.environ.get("AI_PER_HOUR", 30))


@app.route("/api/ai", methods=["POST"])
def ai_ask():
    if not is_admin():   # visitors share a small hourly budget per IP so nobody can drain the Groq quota
        ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0]
        q = _ai_hits[ip]
        while q and time.time() - q[0] > 3600:
            q.popleft()
        if len(q) >= AI_PER_HOUR:
            return jsonify({"ok": False, "code": "rate_limited", "error": "limit"}), 429
        q.append(time.time())
    data = request.get_json() or {}
    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        return jsonify({"ok": False, "code": "invalid_request", "error": "empty prompt"}), 400
    if len(prompt) > 40_000:
        return jsonify({"ok": False, "code": "prompt_too_large", "error": "prompt too long"}), 400
    try:
        text = ai_client.ask(prompt, json_mode=bool(data.get("json")))
        return jsonify({"ok": True, "text": text})
    except ai_client.AIError as e:
        return jsonify({"ok": False, "code": e.code, "error": str(e)}), 503


# ---------- Radio globe ----------
@app.route("/api/stations")
def api_stations():
    """Live news per station (refreshed in the background every 10 min), snapshot until the first refresh lands."""
    d = dict(news_live.get_stations())
    d.pop("brief", None)
    return jsonify(d)


@app.route("/api/brief")
def api_brief():
    """What is moving the market: news pressure per asset (BTC, ETH, alts, gold, oil, S&P 500, dollar) + analysed news feed."""
    return jsonify(news_live.get_brief())


@app.route("/api/tts")
def api_tts():
    """Neural voice for one radio item: ?sid=<station>&i=<item index or -1 for the intro>.
    Only text that is already on a station can be spoken, so this cannot be used as a free TTS service."""
    sid, i = request.args.get("sid", ""), int(request.args.get("i", -1))
    data = news_live.get_stations()
    st = next((s for s in data.get("stations", []) if s.get("id") == sid), None)
    if not st:
        return jsonify({"ok": False, "error": "unknown station"}), 404
    want_en = request.args.get("l") == "en"
    if i < 0:
        text, lang = ((f"This is Crypto Radio, {st['en']}. Here is the latest crypto news.", "en") if want_en else
                      (f"این‌جا رادیو کریپتو، {st['fa']}. خبرهای تازهٔ کریپتو را می‌شنوید.", "fa"))
    elif i < len(st.get("news", [])):
        n = st["news"][i]
        lang = "en" if (want_en or n.get("lang") == "en") else "fa"
        text = n["en"] if lang == "en" else f"{n['t']}. {n['b']}"
    else:
        return jsonify({"ok": False, "error": "unknown item"}), 404
    try:
        audio = tts.speak(text, lang)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:200]}), 503
    return Response(audio, mimetype="audio/mpeg", headers={"Cache-Control": "public, max-age=3600"})


# ---------- Trader ----------
_candle_cache = {"key": None, "at": 0, "data": None}


@app.route("/api/trader/candles")
def api_candles():
    """Live Binance candles for the scanner: {ok, fetched_at, data: {SYM: [[t,o,h,l,c,v], ...]}}"""
    syms = [s.strip().upper() for s in request.args.get("symbols", ",".join(trader_engine.DEFAULT_COINS)).split(",") if s.strip()][:40]
    interval = request.args.get("interval", "1h")
    limit = min(int(request.args.get("limit", 240)), 500)
    key = (tuple(syms), interval, limit)
    if _candle_cache["key"] == key and time.time() - _candle_cache["at"] < 60:
        return jsonify(_candle_cache["data"])

    def one(sym):
        try:
            rows, src = trader_engine.fetch_rows(sym, interval, limit)
            return sym, (rows, src)
        except Exception:
            return sym, None

    res = dict([one(syms[0])]) if syms else {}      # finds the exchange that answers from this server
    with ThreadPoolExecutor(max_workers=8) as ex:
        res.update(dict(ex.map(one, syms[1:])))
    data = {k: v[0] for k, v in res.items() if v}
    sources = sorted({v[1] for v in res.values() if v})
    out = {"ok": len(data) > 0, "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "source": " + ".join(sources), "data": data, "missing": [k for k, v in res.items() if not v]}
    if out["ok"]:
        _candle_cache.update(key=key, at=time.time(), data=out)
    return jsonify(out)


@app.route("/api/markets")
def api_markets():
    """Gold, oil, total crypto market cap and dominance (BTC, ETH, USDT, USDC, stablecoins, Others)."""
    return jsonify(markets.get_markets())


_price_cache = {"key": None, "at": 0, "data": None}


@app.route("/api/prices")
def api_prices():
    """Live prices + 24h change for the ticker: {ok, fetched_at, source, prices: [{c, price, chg24h}]}"""
    syms = [s.strip().upper() for s in request.args.get("symbols", "BTC,ETH,BNB").split(",") if s.strip()][:10]
    key = tuple(syms)
    if _price_cache["key"] == key and time.time() - _price_cache["at"] < 30:
        return jsonify(_price_cache["data"])

    def one(sym):
        try:
            rows, src = trader_engine.fetch_rows(sym, "1h", 25)
            last, prev = rows[-1][4], rows[0][4]
            return {"c": sym, "price": last, "chg24h": last / prev - 1, "source": src}
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=5) as ex:
        prices = [p for p in ex.map(one, syms) if p]
    out = {"ok": bool(prices), "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "source": " + ".join(sorted({p["source"] for p in prices})), "prices": prices}
    if prices:
        _price_cache.update(key=key, at=time.time(), data=out)
    return jsonify(out)


@app.route("/api/trader/send", methods=["POST"])
@admin_required(api=True)
def api_trader_send():
    """Send a drafted post to the admin's Telegram with Approve / Reject buttons."""
    data = request.get_json() or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "متن خالی است"}), 400
    if not telegram_bot.ready():
        return jsonify({"ok": False, "error": "ربات تلگرام روی سرور تنظیم نشده (TELEGRAM_BOT_TOKEN و TELEGRAM_ADMIN_CHAT)"}), 503
    try:
        telegram_bot.send_for_approval(text[:4000], "trader")
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": f"ارسال نشد: {e}"}), 502


# ---------- Telegram agent ----------
@app.route("/telegram/webhook", methods=["POST"])
def telegram_webhook():
    if not hmac.compare_digest(request.headers.get("X-Telegram-Bot-Api-Secret-Token", ""), telegram_bot.webhook_secret()):
        return "forbidden", 403
    try:
        telegram_bot.handle_update(request.get_json(force=True) or {})
    except Exception as e:
        telegram_bot._state["last_error"] = str(e)[:200]
    return "ok"


@app.route("/api/agent/draft", methods=["POST"])
@admin_required(api=True)
def api_agent_draft():
    try:
        return jsonify({"ok": True, "message": telegram_bot.draft_news_now(force=True)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:200]}), 502


@app.route("/api/agent/run", methods=["GET", "POST"])
def api_agent_run():
    """Wake-up call for an outside scheduler (the free server sleeps when idle).
    Safe to leave open: it never drafts more than once per AUTO_POST_MINUTES, and drafts still need your approval."""
    news_live.get_stations()
    res = telegram_bot.tick()
    return jsonify({"ok": True, "drafted": bool(res and "فرستاده شد" in res)})


@app.route("/api/agent/status")
@admin_required(api=True)
def api_agent_status():
    return jsonify(telegram_bot.status())


# ---------- crypto-business crews (optional) ----------
@app.route("/api/prospect", methods=["POST"])
@admin_required(api=True)
def api_prospect():
    data = request.get_json() or {}
    icp = data.get("icp", "channel_admins")
    num = int(data.get("num", 4))
    try:
        from crews.prospect_crew import run_prospecting
        return jsonify({"ok": True, "result": run_prospecting(icp_key=icp, num_leads=num)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e),
                        "hint": "پوشه crypto-business کنار سایت نیست؛ صفحه از هوش مصنوعی سایت استفاده می‌کند."}), 500


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    data = request.get_json() or {}
    text = data.get("text", "").strip()
    focus = data.get("focus", "general")
    try:
        from crews.crypto_crew import run_crypto_analysis
        result = run_crypto_analysis(news_text=text) if text else run_crypto_analysis(focus=focus)
        return jsonify({"ok": True, "result": result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e),
                        "hint": "پوشه crypto-business کنار سایت نیست؛ صفحه از هوش مصنوعی سایت استفاده می‌کند."}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"\nCryptoAI Main Site → http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
