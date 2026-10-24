"""
pro.py — CryptoAI Pro: paid private Telegram channel with instant alerts and a morning brief.

Payments
  • Telegram Stars : a Telegram channel-subscription invite link (Telegram itself charges monthly and removes non-payers).
  • USDT (TRC20)   : the site gives each buyer a unique amount (e.g. 9.37 USDT) to PRO_USDT_TRC20; the server watches the
                     wallet on TronGrid; when the exact amount arrives it issues a one-time invite link to the Pro channel.
                     After 30 days without renewal the member is removed from the channel automatically.

State (members, orders) is kept in memory and backed up as a JSON document pinned in the admin's private chat with the
bot, so nothing is lost when the free server restarts — no database needed.

Environment (Render → Environment; nothing secret goes in code or chat):
  TELEGRAM_PRO_CHANNEL_ID  private Pro channel id (-100…); the bot must be admin there with "invite users" and "ban users"
  PRO_USDT_TRC20           your USDT TRC20 wallet address (public address, not a key)
  PRO_PRICE_USDT           monthly price in USDT (default 9)
  PRO_STARS                monthly price in Telegram Stars (default 500)
  TRONGRID_API_KEY         optional, raises TronGrid limits
"""
from __future__ import annotations

import io
import json
import os
import random
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone

import requests

import telegram_bot as tb

USDT_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
PERIOD = 30 * 24 * 3600
ORDER_TTL = 60 * 60
TEHRAN = timezone(timedelta(hours=3, minutes=30))

_lock = threading.Lock()
S = {"members": {}, "orders": {}, "stars_link": None, "alerted": [], "brief_day": None, "revenue_usdt": 0.0,
     "restored": False, "backup_at": 0, "last_error": None}


def cfg():
    return {
        "pro": os.environ.get("TELEGRAM_PRO_CHANNEL_ID", "").strip(),
        "wallet": os.environ.get("PRO_USDT_TRC20", "").strip(),
        "usdt": float(os.environ.get("PRO_PRICE_USDT", "9") or 9),
        "stars": int(os.environ.get("PRO_STARS", "500") or 500),
        "trongrid_key": os.environ.get("TRONGRID_API_KEY", "").strip(),
    }


def ready() -> bool:
    return tb.ready() and bool(cfg()["pro"])


# ------------------------------------------------------------------ backup / restore (pinned in admin chat)
def _snapshot() -> dict:
    with _lock:
        return {k: S[k] for k in ("members", "orders", "stars_link", "alerted", "brief_day", "revenue_usdt")}


def backup():
    if not tb.ready():
        return
    try:
        c = tb.cfg()
        data = json.dumps(_snapshot(), ensure_ascii=False).encode()
        r = requests.post(tb.API.format(token=c["token"], method="sendDocument"),
                          data={"chat_id": c["admin"], "caption": "پشتیبان مشترکان CryptoAI Pro (این پیام را پاک نکنید)",
                                "disable_notification": "true"},
                          files={"document": ("cryptoai-pro-backup.json", io.BytesIO(data), "application/json")}, timeout=30)
        msg = r.json().get("result") or {}
        if msg.get("message_id"):
            tb.call("pinChatMessage", chat_id=c["admin"], message_id=msg["message_id"], disable_notification=True)
        S["backup_at"] = time.time()
    except Exception as e:
        S["last_error"] = f"backup: {str(e)[:150]}"


def restore():
    if S["restored"] or not tb.ready():
        return
    S["restored"] = True
    try:
        c = tb.cfg()
        chat = tb.call("getChat", chat_id=c["admin"])
        doc = ((chat or {}).get("pinned_message") or {}).get("document")
        if not doc or not str(doc.get("file_name", "")).startswith("cryptoai-pro-backup"):
            return
        f = tb.call("getFile", file_id=doc["file_id"])
        raw = requests.get(f"https://api.telegram.org/file/bot{c['token']}/{f['file_path']}", timeout=20).content
        data = json.loads(raw)
        with _lock:
            for k in ("members", "orders", "stars_link", "alerted", "brief_day", "revenue_usdt"):
                if k in data:
                    S[k] = data[k]
    except Exception as e:
        S["last_error"] = f"restore: {str(e)[:150]}"


# ------------------------------------------------------------------ Telegram Stars
def stars_link() -> str | None:
    c = cfg()
    if not ready():
        return None
    if S["stars_link"]:
        return S["stars_link"]
    try:
        res = tb.call("createChatSubscriptionInviteLink", chat_id=c["pro"], name="CryptoAI Pro · Stars",
                      subscription_period=2592000, subscription_price=c["stars"])
        S["stars_link"] = res["invite_link"]
        backup()
        return S["stars_link"]
    except Exception as e:
        S["last_error"] = f"stars: {str(e)[:150]}"
        return None


# ------------------------------------------------------------------ USDT orders
def new_order() -> dict:
    c = cfg()
    if not (ready() and c["wallet"]):
        raise RuntimeError("پرداخت با تتر هنوز فعال نشده است.")
    with _lock:
        pending = {o["amount"] for o in S["orders"].values() if o["status"] == "pending" and time.time() - o["created"] < ORDER_TTL}
        for _ in range(200):
            amount = round(c["usdt"] + random.randint(1, 99) / 100, 2)
            if amount not in pending:
                break
        oid = secrets.token_urlsafe(9)
        o = {"id": oid, "amount": amount, "created": time.time(), "status": "pending", "tx": None, "link": None, "user": None}
        S["orders"][oid] = o
        # keep the order list short
        if len(S["orders"]) > 500:
            for k in sorted(S["orders"], key=lambda k: S["orders"][k]["created"])[:200]:
                if S["orders"][k]["status"] != "pending":
                    S["orders"].pop(k, None)
    return {"id": oid, "amount": amount, "wallet": c["wallet"], "expires_in": ORDER_TTL}


def _trc20_incoming(since_ms: int):
    c = cfg()
    headers = {"Accept": "application/json"}
    if c["trongrid_key"]:
        headers["TRON-PRO-API-KEY"] = c["trongrid_key"]
    r = requests.get(f"https://api.trongrid.io/v1/accounts/{c['wallet']}/transactions/trc20",
                     params={"only_to": "true", "limit": 50, "contract_address": USDT_CONTRACT, "min_timestamp": since_ms},
                     headers=headers, timeout=12)
    r.raise_for_status()
    return r.json().get("data", [])


def check_order(oid: str) -> dict:
    o = S["orders"].get(oid)
    if not o:
        return {"status": "unknown"}
    if o["status"] == "paid":
        return {"status": "paid", "link": o["link"]}
    if time.time() - o["created"] > ORDER_TTL + 600:
        o["status"] = "expired"
        return {"status": "expired"}
    try:
        used = {x.get("tx") for x in S["orders"].values() if x.get("tx")}
        want = int(round(o["amount"] * 1_000_000))
        for t in _trc20_incoming(int((o["created"] - 120) * 1000)):
            if t.get("to") != cfg()["wallet"] or t.get("transaction_id") in used:
                continue
            if (t.get("token_info") or {}).get("symbol") != "USDT":
                continue
            if int(t.get("value", 0)) == want:
                return _mark_paid(o, t["transaction_id"])
    except Exception as e:
        S["last_error"] = f"tron: {str(e)[:150]}"
    return {"status": "pending", "amount": o["amount"]}


def _mark_paid(o: dict, tx: str) -> dict:
    c = cfg()
    link = tb.call("createChatInviteLink", chat_id=c["pro"], name=f"usdt-{o['id']}", member_limit=1,
                   expire_date=int(time.time()) + 3 * 24 * 3600)["invite_link"]
    with _lock:
        o.update(status="paid", tx=tx, link=link, paid_at=time.time())
        S["revenue_usdt"] = round(S.get("revenue_usdt", 0) + o["amount"], 2)
    try:
        tb.call("sendMessage", chat_id=tb.cfg()["admin"], text=f"💰 اشتراک Pro فروخته شد: {o['amount']} USDT\nتراکنش: {tx[:18]}…")
    except Exception:
        pass
    backup()
    return {"status": "paid", "link": link}


def on_chat_member(upd: dict):
    """A buyer joined the Pro channel through their one-time link: start (or extend) their 30 days."""
    cm = upd.get("chat_member") or {}
    if str((cm.get("chat") or {}).get("id")) != str(cfg()["pro"]):
        return
    new = cm.get("new_chat_member") or {}
    name = ((cm.get("invite_link") or {}).get("name") or "")
    if new.get("status") != "member" or not name.startswith("usdt-"):
        return
    uid = str((new.get("user") or {}).get("id"))
    oid = name[5:]
    with _lock:
        m = S["members"].get(uid, {"exp": 0})
        start = max(time.time(), m.get("exp", 0))
        S["members"][uid] = {"exp": start + PERIOD, "via": "usdt", "order": oid,
                             "name": (new.get("user") or {}).get("first_name", "")}
        if oid in S["orders"]:
            S["orders"][oid]["user"] = uid
    try:
        exp = datetime.fromtimestamp(S["members"][uid]["exp"], TEHRAN).strftime("%Y-%m-%d")
        tb.call("sendMessage", chat_id=uid, text=f"به CryptoAI Pro خوش آمدید 🌟\nاشتراک شما تا {exp} فعال است. برای تمدید، از صفحهٔ Pro سایت دوباره پرداخت کنید.")
    except Exception:
        pass
    backup()


def expire_members():
    """Remove USDT members whose 30 days are over (Stars members are handled by Telegram)."""
    c = cfg()
    now = time.time()
    changed = False
    for uid, m in list(S["members"].items()):
        if m.get("via") != "usdt":
            continue
        left = m["exp"] - now
        if 0 < left < 3 * 24 * 3600 and not m.get("warned"):
            try:
                tb.call("sendMessage", chat_id=uid, text="⏳ اشتراک CryptoAI Pro شما تا ۳ روز دیگر تمام می‌شود. برای تمدید به صفحهٔ Pro سایت بروید.")
            except Exception:
                pass
            m["warned"] = True
            changed = True
        if left <= 0:
            try:
                tb.call("banChatMember", chat_id=c["pro"], user_id=int(uid), until_date=int(now) + 60)
                tb.call("unbanChatMember", chat_id=c["pro"], user_id=int(uid), only_if_banned=True)
                tb.call("sendMessage", chat_id=uid, text="اشتراک CryptoAI Pro شما تمام شد. هر وقت خواستید از صفحهٔ Pro سایت تمدید کنید.")
            except Exception:
                pass
            with _lock:
                S["members"].pop(uid, None)
            changed = True
    if changed:
        backup()


# ------------------------------------------------------------------ Pro content
NAMES = {"BTC": "بیت‌کوین", "ETH": "اتریوم", "ALT": "آلت‌کوین‌ها", "GOLD": "طلا", "OIL": "نفت", "SPX": "S&P 500", "DXY": "دلار"}
STRENGTH = {1: "ملایم", 2: "متوسط", 3: "قوی"}


def _impact_lines(im):
    return "\n".join(f"{'🟢' if x['d'] > 0 else '🔴'} {NAMES.get(x['a'], x['a'])} {'↑' if x['d'] > 0 else '↓'} {STRENGTH.get(x['s'], '')}: {x['w']}"
                     for x in im if x.get("d"))


def send_alerts():
    """Market-moving news (importance 3) goes to the Pro channel at once, with its analysis."""
    import news_live
    if not ready():
        return
    b = news_live.get_brief()
    sent = 0
    for n in b.get("feed", []):
        if n.get("imp", 1) < 3 or n["source"]["url"] in S["alerted"] or time.time() - n["ts"] > 3 * 3600:
            continue
        if sent >= 3:
            break
        text = (f"🚨 خبر فوری بازار\n\n{n['t']}\n\n{n['b']}\n\n"
                f"اثر احتمالی:\n{_impact_lines(n.get('im', [])) or 'اثر روشنی هنوز مشخص نیست.'}\n\n"
                f"🔗 {n['source']['name']}: {n['source']['url']}\n\nCryptoAI Pro · تحلیل است، توصیهٔ سرمایه‌گذاری نیست.")
        try:
            try:   # picture card with the BTC chart and impact bars; plain text if drawing fails
                import post_card
                tb.send_photo(cfg()["pro"], post_card.render_card(n, b.get("assets", [])),
                              post_card.caption(n, b.get("assets", [])))
            except Exception:
                tb.call("sendMessage", chat_id=cfg()["pro"], text=text[:4000], disable_web_page_preview=True)
            S["alerted"] = (S["alerted"] + [n["source"]["url"]])[-300:]
            sent += 1
        except Exception as e:
            S["last_error"] = f"alert: {str(e)[:150]}"
            break
    if sent:
        backup()


def morning_brief(force: bool = False):
    """Every day at 08:00 Tehran time: full brief to Pro, a short teaser to the free channel (after your approval)."""
    import news_live
    now = datetime.now(TEHRAN)
    today = now.strftime("%Y-%m-%d")
    if not force and (now.hour < 8 or S["brief_day"] == today):
        return False
    if not ready():
        return False
    b = news_live.get_brief()
    if not b.get("assets"):
        return False
    lines = []
    for a in b["assets"]:
        icon = "🟢" if a["score"] >= 12 else "🔴" if a["score"] <= -12 else "⚪️"
        lines.append(f"{icon} {a['name']}: {a['label']}" + (f"\n   {a['summary']}" if a.get("summary") else ""))
    top = [n for n in b.get("feed", []) if n.get("imp", 1) >= 2][:5]
    news = "\n".join(f"• {n['t']}" for n in top)
    full = (f"☀️ خلاصهٔ هوشمند صبح · {now.strftime('%Y-%m-%d')}\n\nفشار خبری روی بازارها:\n" + "\n".join(lines) +
            (f"\n\nمهم‌ترین خبرهای ۲۴ ساعت:\n{news}" if news else "") + "\n\nCryptoAI Pro · تحلیل است، توصیهٔ سرمایه‌گذاری نیست.")
    try:
        tb.call("sendMessage", chat_id=cfg()["pro"], text=full[:4000], disable_web_page_preview=True)
    except Exception as e:
        S["last_error"] = f"brief: {str(e)[:150]}"
        return False
    S["brief_day"] = today
    teaser_lines = [l.split("\n")[0] for l in lines[:3]]
    teaser = ("☀️ وضعیت بازار امروز صبح\n\n" + "\n".join(teaser_lines) +
              "\n\nتحلیل کامل همهٔ بازارها و هشدار فوری خبرهای مهم در CryptoAI Pro 🌟")
    try:
        tb.send_for_approval(teaser, "teaser")
    except Exception:
        pass
    backup()
    return True


def tick():
    """Called every minute by the agent loop."""
    if not ready():
        return
    restore()
    try:
        send_alerts()
        morning_brief()
        if int(time.time()) % 3600 < 70:
            expire_members()
    except Exception as e:
        S["last_error"] = str(e)[:150]


def stats() -> dict:
    c = cfg()
    now = time.time()
    with _lock:
        active = [m for m in S["members"].values() if m["exp"] > now]
        return {"ready": ready(), "pro_channel": bool(c["pro"]), "usdt_wallet": bool(c["wallet"]),
                "price_usdt": c["usdt"], "price_stars": c["stars"], "usdt_members": len(active),
                "revenue_usdt": S.get("revenue_usdt", 0), "stars_link": bool(S["stars_link"]),
                "brief_day": S["brief_day"], "backup_at": S["backup_at"], "last_error": S["last_error"],
                "orders_paid": sum(1 for o in S["orders"].values() if o["status"] == "paid")}
