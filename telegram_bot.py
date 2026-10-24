"""
telegram_bot.py — the Telegram agent.

Flow (a human always approves before anything is published):
  1. The agent builds a Persian news post from the live news (news_live) every AUTO_POST_MINUTES,
     or when the admin sends /news to the bot, or from the site's admin panel / trader page.
  2. It sends the draft to the admin chat with two buttons: ✅ تأیید و انتشار / ❌ رد
  3. Telegram calls /telegram/webhook when a button is pressed:
       approve → the text is posted to the channel, the admin message is marked "منتشر شد"
       reject  → the admin message is marked "رد شد", nothing is posted

Environment (set in Render, never in code or chat):
  TELEGRAM_BOT_TOKEN    bot token from @BotFather
  TELEGRAM_ADMIN_CHAT   your own chat id (the person who approves)
  TELEGRAM_CHANNEL_ID   the channel to publish to, e.g. @mychannel or -100123... (bot must be admin there)
  AUTO_POST_MINUTES     how often the agent drafts a post (default 60; 0 = only on request)
  RENDER_EXTERNAL_URL   set by Render automatically; used to register the webhook
"""
from __future__ import annotations

import hashlib
import os
import threading
import time
from datetime import datetime, timezone

import requests

import ai_client

API = "https://api.telegram.org/bot{token}/{method}"
_state = {"webhook_ok": None, "webhook_error": None, "last_draft": None, "last_draft_at": 0.0,
          "posted": [], "drafts_sent": 0, "published": 0, "rejected": 0, "loop": False, "last_error": None}
_seen_urls: set = set()
_lock = threading.Lock()


def cfg():
    return {
        "token": os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(),
        "admin": os.environ.get("TELEGRAM_ADMIN_CHAT", "").strip(),
        "channel": os.environ.get("TELEGRAM_CHANNEL_ID", "").strip(),
        "every": int(os.environ.get("AUTO_POST_MINUTES", "60") or 0),
        "base": os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/"),
    }


def ready() -> bool:
    c = cfg()
    return bool(c["token"] and c["admin"])


def webhook_secret() -> str:
    """Derived from the bot token so nothing extra has to be configured."""
    return hashlib.sha256(("cryptoai-webhook:" + cfg()["token"]).encode()).hexdigest()[:48]


def call(method: str, **params):
    c = cfg()
    r = requests.post(API.format(token=c["token"], method=method), json=params, timeout=20)
    j = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"ok": False, "description": r.text[:200]}
    if not j.get("ok"):
        raise RuntimeError(j.get("description", "telegram error"))
    return j.get("result")


def ensure_webhook():
    """Point Telegram at this site once per process (Render gives us RENDER_EXTERNAL_URL)."""
    c = cfg()
    if not ready() or not c["base"] or _state["webhook_ok"]:
        return
    try:
        call("setWebhook", url=c["base"] + "/telegram/webhook", secret_token=webhook_secret(),
             allowed_updates=["message", "callback_query"], drop_pending_updates=False)
        try:
            call("setMyCommands", commands=[{"command": "news", "description": "ساخت پست خبری تازه برای تأیید"},
                                            {"command": "status", "description": "وضعیت ربات"}])
        except Exception:
            pass
        _state["webhook_ok"], _state["webhook_error"] = True, None
    except Exception as e:
        _state["webhook_ok"], _state["webhook_error"] = False, str(e)[:200]


# ------------------------------------------------------------------ drafts
def send_for_approval(text: str, kind: str = "post") -> dict:
    c = cfg()
    if not ready():
        raise RuntimeError("TELEGRAM_BOT_TOKEN / TELEGRAM_ADMIN_CHAT not set")
    kb = {"inline_keyboard": [[{"text": "✅ تأیید و انتشار", "callback_data": f"approve:{kind}"},
                               {"text": "❌ رد", "callback_data": f"reject:{kind}"}]]}
    note = "" if c["channel"] else "\n\n(کانال تنظیم نشده: TELEGRAM_CHANNEL_ID)"
    res = call("sendMessage", chat_id=c["admin"], text=text[:4000] + note, reply_markup=kb, disable_web_page_preview=True)
    with _lock:
        _state["drafts_sent"] += 1
    return res


def build_news_post(force: bool = False) -> str | None:
    """Persian post from the freshest live headlines not posted before. None if there is nothing new."""
    import news_live
    data = news_live.get_stations()
    if not data.get("live"):
        return None
    items = []
    for st in data["stations"]:
        if not st.get("live"):
            continue
        for n in st["news"]:
            items.append({**n, "station": st["fa"], "notes": st.get("notes", [])})
    items.sort(key=lambda x: -(x.get("ts") or 0))
    fresh = [it for it in items if it["source"]["url"] not in _seen_urls and time.time() - (it.get("ts") or 0) < 6 * 3600]
    if not fresh and not force:
        return None
    pick = (fresh or items)[:4]
    if not pick:
        return None

    text = None
    if ai_client.provider():
        prompt = "\n".join([
            "Write ONE Telegram channel post in Persian (Farsi) for a crypto news channel from these news items.",
            "Use ONLY the facts given. Short lines, a title line, one bullet per news item with its city, a short 'what it may mean for the market' line,",
            "no buy/sell advice, no targets, no entry points. Max 170 words. End with: ⚠️ تحلیل آموزشی است، سیگنال خرید یا فروش نیست.",
            "Do not include links (they are added after your text). Output only the post.",
            "ITEMS:",
        ] + [f"- [{it['station']}] {it['en']} | notes: {[n.get('n') for n in it['notes']][:2]}" for it in pick])
        try:
            text = ai_client.ask(prompt, max_tokens=900).strip()
        except Exception as e:
            _state["last_error"] = f"AI: {e}"[:200]
    if not text:
        text = "📰 خبرهای تازهٔ کریپتو\n\n" + "\n".join(f"• {it['station']}: {it['t']}" for it in pick) + \
               "\n\n⚠️ تحلیل آموزشی است، سیگنال خرید یا فروش نیست."
    links = "\n".join(f"🔗 {it['source']['name']}: {it['source']['url']}" for it in pick)
    for it in pick:
        _seen_urls.add(it["source"]["url"])
    return f"{text}\n\n{links}"


def draft_news_now(force: bool = False) -> str:
    post = build_news_post(force=force)
    if not post:
        return "خبر تازه‌ای برای پست نبود."
    send_for_approval(post, "news")
    with _lock:
        _state["last_draft"], _state["last_draft_at"] = post[:300], time.time()
    return "پیش‌نویس برای تأیید به تلگرام فرستاده شد."


# ------------------------------------------------------------------ webhook
def handle_update(upd: dict) -> None:
    c = cfg()
    admin = str(c["admin"])
    cq = upd.get("callback_query")
    if cq:
        if str(cq.get("from", {}).get("id")) != admin and str(cq.get("message", {}).get("chat", {}).get("id")) != admin:
            call("answerCallbackQuery", callback_query_id=cq["id"], text="اجازه ندارید")
            return
        action = (cq.get("data") or "").split(":")[0]
        msg = cq.get("message") or {}
        body = (msg.get("text") or "").split("\n\n(کانال تنظیم نشده")[0]
        res = ""
        if action == "approve":
            if not c["channel"]:
                res = "⚠️ کانال تنظیم نشده؛ منتشر نشد"
            else:
                try:
                    call("sendMessage", chat_id=c["channel"], text=body, disable_web_page_preview=True)
                    res = "✅ در کانال منتشر شد · " + datetime.now(timezone.utc).strftime("%H:%M UTC")
                    with _lock:
                        _state["published"] += 1
                        _state["posted"] = ([{"at": time.time(), "text": body[:200]}] + _state["posted"])[:10]
                except Exception as e:
                    res = "⚠️ انتشار نشد: " + str(e)[:120]
        elif action == "reject":
            res = "❌ رد شد"
            with _lock:
                _state["rejected"] += 1
        call("answerCallbackQuery", callback_query_id=cq["id"], text=res[:180] or "انجام شد")
        try:
            call("editMessageText", chat_id=msg["chat"]["id"], message_id=msg["message_id"],
                 text=(body + "\n\n— " + res)[:4096], disable_web_page_preview=True)
        except Exception:
            pass
        return

    m = upd.get("message") or {}
    chat = str(m.get("chat", {}).get("id", ""))
    txt = (m.get("text") or "").strip()
    if not txt:
        return
    if chat != admin:
        call("sendMessage", chat_id=chat, text="این ربات فقط برای مدیر کانال است. 🙏")
        return
    if txt.startswith("/news"):
        call("sendMessage", chat_id=chat, text="⏳ در حال ساختن پست از خبرهای زنده…")
        threading.Thread(target=lambda: _safe_reply(chat, lambda: draft_news_now(force=True)), daemon=True).start()
    elif txt.startswith("/status") or txt.startswith("/start"):
        s = status()
        call("sendMessage", chat_id=chat, text=(
            "🤖 ایجنت CryptoAI فعال است\n"
            f"کانال: {c['channel'] or 'تنظیم نشده'}\n"
            f"پست خودکار: {'هر ' + str(c['every']) + ' دقیقه' if c['every'] else 'خاموش'}\n"
            f"پیش‌نویس فرستاده‌شده: {s['drafts_sent']} · منتشرشده: {s['published']} · ردشده: {s['rejected']}\n"
            "دستورها: /news ساخت پست تازه · /status وضعیت"))


def _safe_reply(chat, fn):
    try:
        msg = fn()
        if msg and "فرستاده شد" not in msg:
            call("sendMessage", chat_id=chat, text=msg)
    except Exception as e:
        try:
            call("sendMessage", chat_id=chat, text="⚠️ خطا: " + str(e)[:200])
        except Exception:
            pass


# ------------------------------------------------------------------ schedule
def tick(force_check: bool = False) -> str | None:
    """Called by the background loop and by /api/agent/run. Drafts a post if the interval has passed."""
    c = cfg()
    if not ready():
        return None
    ensure_webhook()
    if not c["every"]:
        return None
    if not force_check and time.time() - _state["last_draft_at"] < c["every"] * 60:
        return None
    try:
        res = draft_news_now(force=False)
        if "نبود" in res:
            _state["last_draft_at"] = time.time() - c["every"] * 60 + 600   # look again in 10 min
        return res
    except Exception as e:
        _state["last_error"] = str(e)[:200]
        return None


def start_loop():
    if _state["loop"]:
        return
    _state["loop"] = True

    def run():
        time.sleep(90)   # let live news load first
        while True:
            try:
                tick()
            except Exception as e:
                _state["last_error"] = str(e)[:200]
            time.sleep(60)
    threading.Thread(target=run, daemon=True).start()


def status() -> dict:
    c = cfg()
    with _lock:
        return {"ready": ready(), "channel_set": bool(c["channel"]), "auto_minutes": c["every"],
                "webhook_ok": _state["webhook_ok"], "webhook_error": _state["webhook_error"],
                "drafts_sent": _state["drafts_sent"], "published": _state["published"], "rejected": _state["rejected"],
                "last_draft": _state["last_draft"], "posted": _state["posted"][:5], "last_error": _state["last_error"]}
