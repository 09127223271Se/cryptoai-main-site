"""
CryptoAI Main Site — یک سایت واحد
کره رادیو + تریدر + تحلیل کریپتو + پیدا کردن مشتری
"""

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from flask import Flask, jsonify, render_template, request, url_for

import ai_client
import trader_engine

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BUSINESS_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "crypto-business"))
if os.path.isdir(BUSINESS_PATH):
    sys.path.insert(0, BUSINESS_PATH)

STATIONS_FILE = os.path.join(BASE_DIR, "static", "data", "stations.json")

app = Flask(__name__, static_folder="static", template_folder="templates")
if trader_engine.trader_bp is not None:
    app.register_blueprint(trader_engine.trader_bp)      # /api/trader/scan, /api/trader/setup/<coin>

PAGES = {"home": "/", "trader": "/trader", "analysis": "/analysis", "sales": "/sales"}


def page(name: str, template: str):
    """Render a page in server mode (links to Flask routes, AI through /api/ai)."""
    return render_template(
        template, page=name, mode="server", api_base="",
        asset=lambda p: url_for("static", filename=p) if p else "/static/",
        link=lambda n: PAGES[n],
    )


# ---------- Pages ----------
@app.route("/")
def home():
    return page("home", "index.html")


@app.route("/trader")
def trader_page():
    return page("trader", "trader.html")


@app.route("/analysis")
def analysis_page():
    return page("analysis", "analysis.html")


@app.route("/sales")
def sales_page():
    return page("sales", "sales.html")


# ---------- Health & AI ----------
@app.route("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "time": datetime.now(timezone.utc).isoformat(),
        "business_module": os.path.isdir(BUSINESS_PATH),
        "ai_provider": ai_client.provider(),
        "telegram": bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_ADMIN_CHAT")),
        "market_data_errors": dict(list(trader_engine.last_errors.items())[:5]),
    })


@app.route("/api/ai/status")
def ai_status():
    p = ai_client.provider()
    return jsonify({"ok": p is not None, "provider": p, "images": False})


@app.route("/api/ai", methods=["POST"])
def ai_ask():
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
    with open(STATIONS_FILE, encoding="utf-8") as f:
        return jsonify(json.load(f))


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

    with ThreadPoolExecutor(max_workers=6) as ex:
        res = dict(ex.map(one, syms))
    data = {k: v[0] for k, v in res.items() if v}
    sources = sorted({v[1] for v in res.values() if v})
    out = {"ok": len(data) > 0, "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "source": " + ".join(sources), "data": data, "missing": [k for k, v in res.items() if not v]}
    if out["ok"]:
        _candle_cache.update(key=key, at=time.time(), data=out)
    return jsonify(out)


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
def api_trader_send():
    """Send a drafted post to the admin's Telegram with Approve / Reject buttons."""
    data = request.get_json() or {}
    text = (data.get("text") or "").strip()
    sym = (data.get("symbol") or "post").upper()
    if not text:
        return jsonify({"ok": False, "error": "متن خالی است"}), 400
    if not (os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_ADMIN_CHAT")):
        return jsonify({"ok": False, "error": "ربات تلگرام روی سرور تنظیم نشده (TELEGRAM_BOT_TOKEN و TELEGRAM_ADMIN_CHAT)"}), 503
    try:
        trader_engine.send_for_approval(text[:4000], f"trader-{sym}-{int(time.time())}")
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": f"ارسال نشد: {e}"}), 502


# ---------- crypto-business crews (optional) ----------
@app.route("/api/prospect", methods=["POST"])
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
