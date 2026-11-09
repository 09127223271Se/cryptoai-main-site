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


def music_embed() -> str:
    """Official Spotify / YouTube player for the music button. MUSIC_EMBED_URL in Render may be a normal share link
    (open.spotify.com/track/…, youtube.com/watch?v=…, youtu.be/…) or an embed link; it is turned into an embed link."""
    import re
    url = (os.environ.get("MUSIC_EMBED_URL", "") or "https://open.spotify.com/track/52SfGEripRfNemuV3g8QH2").strip()
    m = re.search(r"open\.spotify\.com/(?:intl-[a-z]+/)?(?:embed/)?(track|album|playlist|episode)/([A-Za-z0-9]+)", url)
    if m:
        return f"https://open.spotify.com/embed/{m.group(1)}/{m.group(2)}?utm_source=generator&theme=0"
    m = re.search(r"(?:youtube\.com/(?:watch\?v=|embed/|shorts/)|youtu.be/)([A-Za-z0-9_-]{6,})", url)
    if m:
        return f"https://www.youtube-nocookie.com/embed/{m.group(1)}"
    return ""


def socials() -> list:
    """Social profile links for the footer (set in Render; Instagram has a default)."""
    out = []
    for key, label, default in (("INSTAGRAM_URL", "Instagram", "https://www.instagram.com/cryptoglobalfarsi/"),
                                ("TIKTOK_URL", "TikTok", "https://www.tiktok.com/@cryptoglobalfarsi"), ("X_URL", "X", "")):
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
        is_admin=is_admin(), channel=channel_url(lang), alt_url=alt, socials=socials(), music_embed=music_embed(),
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
    return page("home", "trader.html")


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
    return page("trader", "brief.html")


@app.route("/analysis")
def analysis_page():
    return page("analysis", "analysis.html")
