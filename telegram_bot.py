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
        "channel_en": os.environ.get("TELEGRAM_CHANNEL_EN", "").strip(),
        "every": int(os.environ.get("AUTO_POST_MINUTES", "60") or 0),
        "auto": os.environ.get("AUTO_PUBLISH", "1").strip() not in ("0", "false", "no", ""),
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


def send_photo(chat_id, png: bytes, caption: str, reply_markup: dict | None = None):
    """Upload a PNG with an HTML caption."""
    import json as _json
    c = cfg()
    data = {"chat_id": str(chat_id), "caption": caption[:1024], "parse_mode": "HTML"}
    if reply_markup:
        data["reply_markup"] = _json.dumps(reply_markup)
    r = requests.post(API.format(token=c["token"], method="sendPhoto"), data=data,
                      files={"photo": ("cryptoai.png", png, "image/png")}, timeout=40)
    j = r.json()
    if not j.get("ok"):
        raise RuntimeError(j.get("description", "telegram error"))
    return j["result"]


def ensure_webhook():
    """Point Telegram at this site once per process (Render gives us RENDER_EXTERNAL_URL)."""
    c = cfg()
    if not ready() or not c["base"] or _state["webhook_ok"]:
        return
    try:
        call("setWebhook", url=c["base"] + "/telegram/webhook", secret_token=webhook_secret(),
             allowed_updates=["message", "callback_query", "chat_member"], drop_pending_updates=False)
        try:
            call("setMyCommands", commands=[{"command": "start", "description": "Invite link · لینک دعوت"},
                                            {"command": "invite", "description": "My invite link · لینک دعوت من"},
                                            {"command": "me", "description": "My score · امتیاز من"}])
            call("setMyCommands", scope={"type": "chat", "chat_id": int(c["admin"])},
                 commands=[{"command": "news", "description": "ساخت و انتشار پست خبری تازه"},
                           {"command": "status", "description": "وضعیت ربات"},
                           {"command": "kit", "description": "بستهٔ اینستاگرام و تیک‌تاک"},
                           {"command": "invite", "description": "لینک دعوت من"},
                           {"command": "me", "description": "امتیاز من"}])
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


_drafts: dict = {}   # admin message id -> HTML caption (to republish with formatting)


def _remember(url):
    _seen_urls.add(url)
    try:   # survives server restarts (kept in the pinned backup file)
        import pro
        pro.S["posted_urls"] = (pro.S.get("posted_urls", []) + [url])[-300:]
        pro.backup()
    except Exception:
        pass


def _load_seen():
    try:
        import pro
        pro.restore()
        _seen_urls.update(pro.S.get("posted_urls", []))
    except Exception:
        pass


def _publish(lang, channel, n, assets, png=None, cap=None):
    """Post one story to one channel in its language. Returns the channel message id."""
    import post_card
    if cap is None:
        cap = post_card.caption(n, assets) if lang == "fa" else post_card.caption_en(n, assets)
    if png is None:
        try:
            png = post_card.render_card(n, assets, lang)
        except Exception as e:
            _state["last_error"] = f"card {lang}: {e}"[:200]
    btns = post_card.channel_buttons(lang)
    if png:
        return send_photo(channel, png, cap, btns)["message_id"]
    return call("sendMessage", chat_id=channel, text=cap, parse_mode="HTML", disable_web_page_preview=True,
                **({"reply_markup": btns} if btns else {}))["message_id"]


def draft_news_now(force: bool = False, breaking_only: bool = False) -> str:
    """Pick the most market-moving fresh story and draw its card.
    AUTO_PUBLISH on (default): post it to the channel at once and notify the admin (with a delete button).
    AUTO_PUBLISH=0: send it to the admin with approve / reject buttons."""
    import post_card
    _load_seen()
    n, assets = post_card.pick_news(_seen_urls, force=force)
    if not n or (breaking_only and n.get("imp", 1) < 3):
        return "خبر تازه‌ای برای پست نبود."
    c = cfg()
    cap = post_card.caption(n, assets)
    try:
        png = post_card.render_card(n, assets)
    except Exception as e:
        _state["last_error"] = f"card: {e}"[:200]
        png = None

    if c["auto"] and (c["channel"] or c["channel_en"]):
        done = []
        for lang, ch in (("fa", c["channel"]), ("en", c["channel_en"])):
            if not ch:
                continue
            try:
                mid = _publish(lang, ch, n, assets, png if lang == "fa" else None, cap if lang == "fa" else None)
                done.append((lang, mid))
            except Exception as e:
                _state["last_error"] = f"publish {lang}: {e}"[:200]
        if not done:
            return "انتشار نشد: " + str(_state["last_error"])
        _remember(n["source"]["url"])
        with _lock:
            _state["published"] += 1
            _state["posted"] = ([{"at": time.time(), "text": n.get("t", "")[:200]}] + _state["posted"])[:10]
            _state["last_draft"], _state["last_draft_at"] = n.get("t", "")[:300], time.time()
        try:
            btn = [{"text": "🗑 حذف از کانال فارسی" if lg == "fa" else "🗑 حذف از کانال انگلیسی",
                    "callback_data": f"del:{lg}:{mid}"} for lg, mid in done]
            call("sendMessage", chat_id=c["admin"], text=f"📢 پست جدید منتشر شد ({' + '.join('فارسی' if lg == 'fa' else 'انگلیسی' for lg, _ in done)}):\n{n.get('t', '')}",
                 reply_markup={"inline_keyboard": [btn]})
        except Exception:
            pass
        return "پست در کانال منتشر شد."

    kb = {"inline_keyboard": [[{"text": "✅ تأیید و انتشار", "callback_data": "approve:card"},
                               {"text": "❌ رد", "callback_data": "reject:card"}]]}
    if png:
        msg = send_photo(c["admin"], png, cap, kb)
    else:
        msg = call("sendMessage", chat_id=c["admin"], text=cap, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
    if not c["channel"]:
        call("sendMessage", chat_id=c["admin"], text="(کانال تنظیم نشده: TELEGRAM_CHANNEL_ID)")
    _drafts[msg["message_id"]] = {"cap": cap, "n": n, "assets": assets}
    while len(_drafts) > 50:
        _drafts.pop(next(iter(_drafts)))
    _remember(n["source"]["url"])
    with _lock:
        _state["drafts_sent"] += 1
        _state["last_draft"], _state["last_draft_at"] = n.get("t", "")[:300], time.time()
    return "پیش‌نویس برای تأیید به تلگرام فرستاده شد."


# ------------------------------------------------------------------ webhook
def handle_update(upd: dict) -> None:
    c = cfg()
    if upd.get("chat_member"):
        import pro
        import growth
        pro.on_chat_member(upd)
        try:
            growth.on_channel_member(upd)
        except Exception as e:
            _state["last_error"] = f"growth member: {e}"[:200]
        return
    admin = str(c["admin"])
    cq = upd.get("callback_query")
    if cq and (cq.get("data") or "").startswith(("g:", "gs:")):
        import growth
        growth.on_vote(cq)
        return
    if cq:
        if str(cq.get("from", {}).get("id")) != admin and str(cq.get("message", {}).get("chat", {}).get("id")) != admin:
            call("answerCallbackQuery", callback_query_id=cq["id"], text="اجازه ندارید")
            return
        action = (cq.get("data") or "").split(":")[0]
        if action == "noop":
            call("answerCallbackQuery", callback_query_id=cq["id"])
            return
        if action == "del":
            parts_ = (cq.get("data") or "").split(":")
            lg, mid = (parts_[1], parts_[2]) if len(parts_) > 2 else ("fa", parts_[1])
            try:
                call("deleteMessage", chat_id=c["channel_en"] if lg == "en" else c["channel"], message_id=int(mid))
                res = "🗑 از کانال حذف شد"
            except Exception as e:
                res = "⚠️ حذف نشد: " + str(e)[:100]
            call("answerCallbackQuery", callback_query_id=cq["id"], text=res)
            m0 = cq.get("message") or {}
            try:
                call("editMessageReplyMarkup", chat_id=m0["chat"]["id"], message_id=m0["message_id"],
                     reply_markup={"inline_keyboard": [[{"text": res, "callback_data": "noop"}]]})
            except Exception:
                pass
            return
        msg = cq.get("message") or {}
        photo = (msg.get("photo") or [{}])[-1].get("file_id")
        dr = _drafts.pop(msg.get("message_id"), None)
        html_cap = dr["cap"] if isinstance(dr, dict) else dr
        body = (msg.get("text") or msg.get("caption") or "").split("\n\n(کانال تنظیم نشده")[0]
        res = ""
        if action == "approve":
            if not c["channel"]:
                res = "⚠️ کانال تنظیم نشده؛ منتشر نشد"
            else:
                try:
                    import post_card
                    btns = post_card.channel_buttons()
                    extra = {"reply_markup": btns} if btns else {}
                    if photo:
                        if html_cap:
                            call("sendPhoto", chat_id=c["channel"], photo=photo, caption=html_cap, parse_mode="HTML", **extra)
                        else:
                            call("sendPhoto", chat_id=c["channel"], photo=photo, caption=body[:1024], **extra)
                    elif html_cap:
                        call("sendMessage", chat_id=c["channel"], text=html_cap, parse_mode="HTML", disable_web_page_preview=True, **extra)
                    else:
                        call("sendMessage", chat_id=c["channel"], text=body, disable_web_page_preview=True, **extra)
                    res = "✅ در کانال منتشر شد · " + datetime.now(timezone.utc).strftime("%H:%M UTC")
                    if isinstance(dr, dict) and c["channel_en"]:
                        try:
                            _publish("en", c["channel_en"], dr["n"], dr["assets"])
                            res += " · EN ✅"
                        except Exception as e:
                            res += " · EN ⚠️"
                            _state["last_error"] = f"publish en: {e}"[:200]
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
        try:   # replace the two buttons with the result
            call("editMessageReplyMarkup", chat_id=msg["chat"]["id"], message_id=msg["message_id"],
                 reply_markup={"inline_keyboard": [[{"text": res[:60] or "انجام شد", "callback_data": "noop"}]]})
        except Exception:
            pass
        return

    m = upd.get("message") or {}
    chat = str(m.get("chat", {}).get("id", ""))
    txt = (m.get("text") or "").strip()
    if not txt:
        return
    if chat != admin or txt.startswith(("/invite", "/me")) or (txt.startswith("/start ") and "ref" in txt):
        if (m.get("chat") or {}).get("type") == "private":
            import growth
            growth.on_private(m)
        return
    if txt.startswith("/kit"):
        call("sendMessage", chat_id=chat, text="⏳ در حال ساختن بستهٔ اینستاگرام و تیک‌تاک…")
        def _kit():
            import social
            return social.send_kit()
        threading.Thread(target=lambda: _safe_reply(chat, _kit), daemon=True).start()
        return
    if txt.startswith("/news"):
        call("sendMessage", chat_id=chat, text="⏳ در حال ساختن پست از خبرهای زنده…")
        threading.Thread(target=lambda: _safe_reply(chat, lambda: draft_news_now(force=True)), daemon=True).start()
    elif txt.startswith("/status") or txt.startswith("/start"):
        s = status()
        call("sendMessage", chat_id=chat, text=(
            "🤖 ایجنت CryptoAI فعال است\n"
            f"کانال فارسی: {c['channel'] or 'تنظیم نشده'} · کانال انگلیسی: {c['channel_en'] or 'تنظیم نشده'}\n"
            f"پست خودکار: {'هر ' + str(c['every']) + ' دقیقه' if c['every'] else 'خاموش'}"
            f" · {'انتشار مستقیم' if c['auto'] else 'با تأیید شما'} · خبر فوری بلافاصله\n"
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
    since = time.time() - _state["last_draft_at"]
    try:
        if not force_check and since < c["every"] * 60:
            if since > 20 * 60:            # breaking news (importance 3) does not wait for the hourly slot
                res = draft_news_now(force=False, breaking_only=True)
                return res if "نبود" not in res else None
            return None
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
            try:
                import pro
                pro.tick()
            except Exception as e:
                _state["last_error"] = "pro: " + str(e)[:180]
            try:
                import social
                social.tick()
            except Exception as e:
                _state["last_error"] = "social: " + str(e)[:180]
            try:
                import growth
                growth.tick()
            except Exception as e:
                _state["last_error"] = "growth: " + str(e)[:180]
            time.sleep(60)
    threading.Thread(target=run, daemon=True).start()


def status() -> dict:
    c = cfg()
    with _lock:
        return {"ready": ready(), "channel_set": bool(c["channel"]), "auto_minutes": c["every"],
                "webhook_ok": _state["webhook_ok"], "webhook_error": _state["webhook_error"],
                "drafts_sent": _state["drafts_sent"], "published": _state["published"], "rejected": _state["rejected"],
                "last_draft": _state["last_draft"], "posted": _state["posted"][:5], "last_error": _state["last_error"]}
