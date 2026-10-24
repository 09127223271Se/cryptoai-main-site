"""
growth.py — audience growth for the public channels (Persian and English).

1) "Up or Down?" daily game
   • Every day at GAME_HOUR_UTC (default 15:00 UTC) the bot posts a round in each public channel:
     "Will Bitcoin be higher or lower this time tomorrow?" with ⬆️ / ⬇️ buttons (one vote per person,
     voting closes after GAME_LOCK_HOURS, default 2).
   • 24 hours later the round is settled against the live BTC price, the result and the weekly leaderboard
     are posted, and the next round starts.
   • Every Monday the week's best predictor wins 30 days of CryptoAI Pro.

2) Invite friends
   • Anyone who opens the bot gets a personal invite link to the channel.
   • Every 3 new members who join through it = 7 days of CryptoAI Pro for the inviter.

State lives in pro.S["growth"] and is saved in the pinned backup file, so a restart loses nothing.
No buy/sell advice anywhere: the game is a prediction contest, not a signal.
"""
from __future__ import annotations

import html
import os
import threading
import time
from datetime import datetime, timezone

import pro
import telegram_bot as tb

GAME_HOUR = int(os.environ.get("GAME_HOUR_UTC", "15") or 15)
LOCK_H = float(os.environ.get("GAME_LOCK_HOURS", "2") or 2)
REF_NEED = int(os.environ.get("REF_FRIENDS", "3") or 3)
REF_DAYS = int(os.environ.get("REF_PRO_DAYS", "7") or 7)
WEEK_PRIZE_DAYS = 30
DAY = 24 * 3600

_lock = threading.Lock()
_rt = {"bot": None, "edit_at": {}, "dirty": False, "saved_at": 0.0, "last_error": None}

TXT = {
    "fa": {
        "round": "🎮 <b>بازی «بالا یا پایین؟»</b> · دور {n}\n\n"
                 "بیت‌کوین الان: <b>{p}</b>\n"
                 "فردا همین ساعت <b>بالاتر</b> است یا <b>پایین‌تر</b>؟\n\n"
                 "⏳ رأی‌گیری تا {lock} ساعت دیگر باز است\n"
                 "🏆 بهترین پیش‌بینی‌کنندهٔ هفته = <b>یک ماه Pro رایگان</b>\n"
                 "🎁 {need} دوست دعوت کن = <b>{days} روز Pro رایگان</b>",
        "up": "⬆️ بالا", "down": "⬇️ پایین", "invite": "🎁 لینک دعوت من", "me": "🏆 امتیاز من",
        "locked": "🔒 رأی‌گیری بسته شد", "voted": "رأی شما ثبت شد: {v} ✅ فردا نتیجه اعلام می‌شود.",
        "closed": "رأی‌گیری این دور بسته شده؛ دور بعدی فردا.", "changed": "رأی شما عوض شد: {v}",
        "result": "📣 <b>نتیجهٔ دور {n}</b>\n\nبیت‌کوین از {p0} به {p1} رسید {arrow}\n"
                  "<b>{ok}</b> نفر از {tot} نفر درست گفتند.{none}",
        "nobody": "\nاین دور کسی شرکت نکرد.",
        "flat": "قیمت تقریباً تغییری نکرد؛ این دور برنده ندارد.",
        "board": "\n\n🏆 <b>جدول این هفته</b>\n{rows}",
        "board_empty": "\n\n🏆 جدول این هفته هنوز خالی است. اولین نفر باشید!",
        "week_win": "🥇 <b>برندهٔ هفته:</b> {name} با {pts} پیش‌بینی درست!\n"
                    "جایزه: یک ماه CryptoAI Pro رایگان 🎉\n{claim}",
        "claim": "برنده عزیز، برای دریافت جایزه ربات را باز کنید و Start بزنید: {bot}",
        "my": "امتیاز این هفته: {w} · رتبه: {r}\nکل پیش‌بینی‌های درست: {t} · بهترین رکورد پشت‌سرهم: {s}\nدعوت‌های موفق: {refs}",
        "start": "سلام {name} 👋 به CryptoAI خوش آمدید.\n\n"
                 "🎁 <b>لینک دعوت اختصاصی شما:</b>\n{link}\n\n"
                 "هر {need} نفر که با این لینک عضو کانال شوند = <b>{days} روز CryptoAI Pro رایگان</b>.\n"
                 "تا الان: <b>{cnt}</b> نفر{next}\n\n"
                 "🎮 هر روز در کانال در بازی «بالا یا پایین؟» شرکت کنید؛ بهترین پیش‌بینی‌کنندهٔ هفته یک ماه Pro می‌برد.\n\n"
                 "دستورها: /invite لینک دعوت · /me امتیاز من",
        "next": " (برای جایزهٔ بعدی {left} نفر دیگر)",
        "nolink": "لینک دعوت فعلاً ساخته نشد؛ کمی بعد دوباره /invite را بفرستید.",
        "ref_join": "🎉 یک نفر با لینک شما عضو کانال شد! تا الان: {cnt} نفر.",
        "gift": "🎁 تبریک! {why}\nلینک ورود یک‌بارمصرف به کانال CryptoAI Pro ({days} روز):\n{link}",
        "gift_ext": "🎁 تبریک! {why}\nاشتراک Pro شما {days} روز تمدید شد.",
        "gift_wait": "🎁 تبریک! {why}\nکانال Pro به‌زودی راه می‌افتد و جایزهٔ شما همان موقع فعال می‌شود.",
        "why_ref": "{need} نفر با لینک شما عضو شدند.", "why_week": "شما برندهٔ هفتهٔ بازی «بالا یا پایین؟» شدید.",
        "foot": "\n\n⚠️ بازی پیش‌بینی است، سیگنال خرید یا فروش نیست.",
    },
    "en": {
        "round": "🎮 <b>Up or Down?</b> · round {n}\n\n"
                 "Bitcoin now: <b>{p}</b>\n"
                 "Will it be <b>higher</b> or <b>lower</b> this time tomorrow?\n\n"
                 "⏳ Voting is open for {lock} hours\n"
                 "🏆 Best predictor of the week = <b>1 month of Pro free</b>\n"
                 "🎁 Invite {need} friends = <b>{days} days of Pro free</b>",
        "up": "⬆️ Up", "down": "⬇️ Down", "invite": "🎁 My invite link", "me": "🏆 My score",
        "locked": "🔒 Voting closed", "voted": "Vote saved: {v} ✅ Results tomorrow.",
        "closed": "Voting for this round is closed; next round tomorrow.", "changed": "Vote changed: {v}",
        "result": "📣 <b>Round {n} result</b>\n\nBitcoin went from {p0} to {p1} {arrow}\n"
                  "<b>{ok}</b> of {tot} players got it right.{none}",
        "nobody": "\nNobody played this round.",
        "flat": "The price barely moved; no winners this round.",
        "board": "\n\n🏆 <b>This week's leaderboard</b>\n{rows}",
        "board_empty": "\n\n🏆 This week's leaderboard is empty. Be the first!",
        "week_win": "🥇 <b>Winner of the week:</b> {name} with {pts} correct calls!\n"
                    "Prize: 1 month of CryptoAI Pro 🎉\n{claim}",
        "claim": "Winner, open the bot and press Start to claim your prize: {bot}",
        "my": "This week: {w} points · rank: {r}\nTotal correct calls: {t} · best streak: {s}\nFriends invited: {refs}",
        "start": "Hi {name} 👋 Welcome to CryptoAI.\n\n"
                 "🎁 <b>Your personal invite link:</b>\n{link}\n\n"
                 "Every {need} people who join the channel through it = <b>{days} days of CryptoAI Pro free</b>.\n"
                 "So far: <b>{cnt}</b>{next}\n\n"
                 "🎮 Play “Up or Down?” in the channel every day; the best predictor of the week wins a month of Pro.\n\n"
                 "Commands: /invite invite link · /me my score",
        "next": " ({left} more for your next reward)",
        "nolink": "Could not create your invite link yet; send /invite again in a minute.",
        "ref_join": "🎉 Someone joined the channel with your link! So far: {cnt}.",
        "gift": "🎁 Congratulations! {why}\nYour one-time link to the CryptoAI Pro channel ({days} days):\n{link}",
        "gift_ext": "🎁 Congratulations! {why}\nYour Pro subscription was extended by {days} days.",
        "gift_wait": "🎁 Congratulations! {why}\nThe Pro channel opens soon and your prize starts then.",
        "why_ref": "{need} people joined with your link.", "why_week": "You won this week's “Up or Down?” game.",
        "foot": "\n\n⚠️ A prediction game, not a buy/sell signal.",
    },
}


# ------------------------------------------------------------------ state
def G() -> dict:
    g = pro.S.setdefault("growth", {})
    g.setdefault("game", {})          # lang -> current round
    g.setdefault("round_no", {})      # lang -> counter
    g.setdefault("scores", {})        # lang -> uid -> {name, week, total, streak, best}
    g.setdefault("week", "")
    g.setdefault("refs", {})          # uid -> {name, lang, links:{lang:url}, joined:[uid], rewarded:int}
    g.setdefault("counted", [])       # member uids already credited to someone
    g.setdefault("pending", {})       # uid -> [{days, why, lang}]
    g.setdefault("users", {})         # uid -> lang (people who started the bot)
    return g


def _dirty():
    _rt["dirty"] = True


def channels():
    c = tb.cfg()
    return [(lang, ch) for lang, ch in (("fa", c["channel"]), ("en", c["channel_en"])) if ch]


def bot_link(param: str = "") -> str:
    if not _rt["bot"]:
        try:
            _rt["bot"] = tb.call("getMe")["username"]
        except Exception:
            return ""
    return f"https://t.me/{_rt['bot']}" + (f"?start={param}" if param else "")


def btc_price() -> float | None:
    try:
        import trader_engine
        rows, _ = trader_engine.fetch_rows("BTC", "1h", 25)
        return float(rows[-1][4])
    except Exception as e:
        _rt["last_error"] = f"price: {e}"[:150]
        return None


def _money(v):
    return f"${v:,.0f}"


def _name(user: dict) -> str:
    n = (user.get("first_name") or "") + (" " + user["last_name"] if user.get("last_name") else "")
    n = n.strip() or (("@" + user["username"]) if user.get("username") else "user")
    return n[:24]


def _week() -> str:
    y, w, _ = datetime.now(timezone.utc).isocalendar()
    return f"{y}-W{w:02d}"


# ------------------------------------------------------------------ game
def _kb(lang, rnd):
    t = TXT[lang]
    up = sum(1 for v in rnd["votes"].values() if v == "u")
    dn = sum(1 for v in rnd["votes"].values() if v == "d")
    rid = rnd["id"]
    if rnd.get("locked"):
        row1 = [{"text": f"{t['locked']} · ⬆️ {up} · ⬇️ {dn}", "callback_data": f"gs:{lang}"}]
    else:
        row1 = [{"text": f"{t['up']} ({up})", "callback_data": f"g:{lang}:{rid}:u"},
                {"text": f"{t['down']} ({dn})", "callback_data": f"g:{lang}:{rid}:d"}]
    row2 = [{"text": t["me"], "callback_data": f"gs:{lang}"}]
    link = bot_link(f"ref_{lang}")
    if link:
        row2.insert(0, {"text": t["invite"], "url": link})
    return {"inline_keyboard": [row1, row2]}


def _board(lang, top=5) -> str:
    t = TXT[lang]
    sc = G()["scores"].get(lang, {})
    rows = sorted(((v["week"], v.get("streak", 0), uid, v) for uid, v in sc.items() if v.get("week", 0) > 0), reverse=True)[:top]
    if not rows:
        return t["board_empty"]
    medals = ["🥇", "🥈", "🥉", "4.", "5."]
    lines = "\n".join(f"{medals[i]} {html.escape(v['name'])} · {w}" for i, (w, _, _, v) in enumerate(rows))
    return t["board"].format(rows=lines)


def open_round(lang, ch):
    p = btc_price()
    if not p:
        return False
    g = G()
    n = g["round_no"].get(lang, 0) + 1
    t = TXT[lang]
    rnd = {"id": int(time.time()), "n": n, "price": p, "start": time.time(), "votes": {}, "names": {}, "locked": False}
    text = t["round"].format(n=n, p=_money(p), lock=f"{LOCK_H:g}", need=REF_NEED, days=REF_DAYS) + t["foot"]
    msg = tb.call("sendMessage", chat_id=ch, text=text, parse_mode="HTML", reply_markup=_kb(lang, rnd),
                  disable_web_page_preview=True)
    rnd["msg"] = msg["message_id"]
    with _lock:
        g["game"][lang] = rnd
        g["round_no"][lang] = n
    _dirty()
    return True


def settle_round(lang, ch):
    g = G()
    rnd = g["game"].get(lang)
    if not rnd:
        return
    p1 = btc_price()
    if not p1:
        return
    t = TXT[lang]
    move = p1 / rnd["price"] - 1
    res = "u" if move > 0.0005 else "d" if move < -0.0005 else None
    sc = g["scores"].setdefault(lang, {})
    ok = 0
    with _lock:
        for uid, v in rnd["votes"].items():
            s = sc.setdefault(uid, {"name": rnd["names"].get(uid, "user"), "week": 0, "total": 0, "streak": 0, "best": 0})
            s["name"] = rnd["names"].get(uid, s["name"])
            if res and v == res:
                ok += 1
                s["week"] += 1; s["total"] += 1; s["streak"] += 1
                s["best"] = max(s["best"], s["streak"])
            elif res:
                s["streak"] = 0
        g["game"][lang] = None
    arrow = "⬆️" if res == "u" else "⬇️" if res == "d" else "↔️"
    tot = len(rnd["votes"])
    text = t["result"].format(n=rnd["n"], p0=_money(rnd["price"]), p1=_money(p1), arrow=arrow, ok=ok, tot=tot,
                              none=t["nobody"] if not tot else "")
    if not res:
        text += "\n" + t["flat"]
    text += _board(lang)
    try:
        tb.call("sendMessage", chat_id=ch, text=text, parse_mode="HTML", reply_to_message_id=rnd.get("msg"),
                allow_sending_without_reply=True)
    except Exception as e:
        _rt["last_error"] = f"settle {lang}: {e}"[:150]
    _dirty()


def weekly_prize():
    """At the first settle of a new ISO week: the best predictor of last week in each channel wins 30 days of Pro."""
    g = G()
    wk = _week()
    if not g["week"]:
        g["week"] = wk
        return
    if g["week"] == wk:
        return
    for lang, ch in channels():
        sc = g["scores"].get(lang, {})
        best = sorted(((v["week"], v.get("best", 0), uid) for uid, v in sc.items() if v.get("week", 0) > 0), reverse=True)
        if best:
            pts, _, uid = best[0]
            name = sc[uid]["name"]
            t = TXT[lang]
            delivered = grant(uid, WEEK_PRIZE_DAYS, t["why_week"], lang)
            claim = "" if delivered else t["claim"].format(bot=bot_link(f"ref_{lang}"))
            try:
                tb.call("sendMessage", chat_id=ch, text=t["week_win"].format(name=html.escape(name), pts=pts, claim=claim),
                        parse_mode="HTML", disable_web_page_preview=True)
            except Exception:
                pass
        with _lock:
            for v in sc.values():
                v["week"] = 0
    g["week"] = wk
    _dirty()


def lock_rounds():
    g = G()
    for lang, ch in channels():
        rnd = g["game"].get(lang)
        if rnd and not rnd.get("locked") and time.time() - rnd["start"] > LOCK_H * 3600:
            rnd["locked"] = True
            try:
                tb.call("editMessageReplyMarkup", chat_id=ch, message_id=rnd["msg"], reply_markup=_kb(lang, rnd))
            except Exception:
                pass
            _dirty()


def game_tick():
    g = G()
    now = datetime.now(timezone.utc)
    lock_rounds()
    for lang, ch in channels():
        rnd = g["game"].get(lang)
        if rnd and time.time() - rnd["start"] >= DAY - 90:
            weekly_prize()
            settle_round(lang, ch)
            rnd = None
        if not rnd and now.hour == GAME_HOUR:
            last = g.get("opened_day", {}).get(lang)
            today = now.strftime("%Y-%m-%d")
            if last != today:
                if open_round(lang, ch):
                    g.setdefault("opened_day", {})[lang] = today


def on_vote(cq: dict) -> bool:
    """Callback from a channel post. Returns True if it was ours."""
    data = cq.get("data") or ""
    user = cq.get("from") or {}
    uid = str(user.get("id"))
    if data.startswith("gs:"):
        lang = data.split(":")[1] if ":" in data else "fa"
        tb.call("answerCallbackQuery", callback_query_id=cq["id"], text=my_stats(uid, lang)[:190], show_alert=True)
        return True
    if not data.startswith("g:"):
        return False
    _, lang, rid, v = (data.split(":") + ["", "", "", ""])[:4]
    t = TXT.get(lang, TXT["fa"])
    rnd = G()["game"].get(lang)
    if not rnd or str(rnd["id"]) != rid or rnd.get("locked") or time.time() - rnd["start"] > LOCK_H * 3600:
        tb.call("answerCallbackQuery", callback_query_id=cq["id"], text=t["closed"])
        return True
    label = t["up"] if v == "u" else t["down"]
    with _lock:
        before = rnd["votes"].get(uid)
        rnd["votes"][uid] = "u" if v == "u" else "d"
        rnd["names"][uid] = _name(user)
    tb.call("answerCallbackQuery", callback_query_id=cq["id"],
            text=(t["changed"] if before and before != rnd["votes"][uid] else t["voted"]).format(v=label))
    _dirty()
    # refresh the counts on the post, at most every 4 seconds per round
    key = f"{lang}:{rid}"
    if time.time() - _rt["edit_at"].get(key, 0) > 4:
        _rt["edit_at"][key] = time.time()
        ch = dict(channels()).get(lang)
        try:
            tb.call("editMessageReplyMarkup", chat_id=ch, message_id=rnd["msg"], reply_markup=_kb(lang, rnd))
        except Exception:
            pass
    return True


def my_stats(uid: str, lang: str) -> str:
    t = TXT.get(lang, TXT["fa"])
    sc = G()["scores"].get(lang, {})
    s = sc.get(uid, {"week": 0, "total": 0, "best": 0})
    order = sorted(sc, key=lambda u: -sc[u].get("week", 0))
    rank = (order.index(uid) + 1) if uid in sc and s.get("week", 0) > 0 else "–"
    refs = len(G()["refs"].get(uid, {}).get("joined", []))
    return t["my"].format(w=s.get("week", 0), r=rank, t=s.get("total", 0), s=s.get("best", 0), refs=refs)


# ------------------------------------------------------------------ referrals and prizes
def invite_link(uid: str, lang: str, name: str) -> str | None:
    g = G()
    r = g["refs"].setdefault(uid, {"name": name, "lang": lang, "links": {}, "joined": [], "rewarded": 0})
    r["name"] = name
    if r["links"].get(lang):
        return r["links"][lang]
    ch = dict(channels()).get(lang) or (channels()[0][1] if channels() else None)
    if not ch:
        return None
    try:
        link = tb.call("createChatInviteLink", chat_id=ch, name=f"ref-{uid}"[:32])["invite_link"]
    except Exception as e:
        _rt["last_error"] = f"invite link: {e}"[:150]
        return None
    r["links"][lang] = link
    _dirty()
    return link


def on_private(m: dict):
    """A visitor (not the admin) wrote to the bot: welcome, invite link, score, pending prizes."""
    user = m.get("from") or {}
    uid = str(user.get("id"))
    txt = (m.get("text") or "").strip()
    param = txt.split(" ", 1)[1] if txt.startswith("/start ") else ""
    g = G()
    lang = "en" if param.endswith("en") else "fa" if param.endswith("fa") else \
        g["users"].get(uid) or ("fa" if (user.get("language_code") or "").startswith("fa") else "en")
    if lang == "en" and not tb.cfg()["channel_en"]:
        lang = "fa"
    if lang == "fa" and not tb.cfg()["channel"] and tb.cfg()["channel_en"]:
        lang = "en"
    g["users"][uid] = lang
    t = TXT[lang]
    deliver_pending(uid)
    if txt.startswith("/me"):
        tb.call("sendMessage", chat_id=uid, text=my_stats(uid, lang))
        return
    link = invite_link(uid, lang, _name(user))
    if not link:
        tb.call("sendMessage", chat_id=uid, text=t["nolink"])
        return
    cnt = len(g["refs"][uid]["joined"])
    left = REF_NEED - cnt % REF_NEED
    tb.call("sendMessage", chat_id=uid, parse_mode="HTML", disable_web_page_preview=True,
            text=t["start"].format(name=html.escape(_name(user)), link=link, need=REF_NEED, days=REF_DAYS, cnt=cnt,
                                   next=t["next"].format(left=left)))
    _dirty()


def on_channel_member(upd: dict):
    """Someone joined a public channel. If it was through a personal invite link, credit the inviter."""
    cm = upd.get("chat_member") or {}
    chat = str((cm.get("chat") or {}).get("id"))
    chans = {lang: ch for lang, ch in channels()}
    uname = (cm.get("chat") or {}).get("username")
    lang = next((l for l, ch in chans.items() if ch == chat or (uname and ch.lstrip("@").lower() == uname.lower())), None)
    if not lang:
        return
    new = cm.get("new_chat_member") or {}
    old = cm.get("old_chat_member") or {}
    name = (cm.get("invite_link") or {}).get("name") or ""
    if new.get("status") != "member" or old.get("status") in ("member", "administrator", "creator") or not name.startswith("ref-"):
        return
    ref = name[4:]
    member = str((new.get("user") or {}).get("id"))
    g = G()
    if member == ref or member in g["counted"] or ref not in g["refs"]:
        return
    with _lock:
        g["counted"] = (g["counted"] + [member])[-20000:]
        r = g["refs"][ref]
        r["joined"].append(member)
        cnt = len(r["joined"])
    rl = r.get("lang", lang)
    t = TXT[rl]
    try:
        tb.call("sendMessage", chat_id=ref, text=t["ref_join"].format(cnt=cnt))
    except Exception:
        pass
    if cnt // REF_NEED > r.get("rewarded", 0):
        r["rewarded"] = cnt // REF_NEED
        grant(ref, REF_DAYS, t["why_ref"].format(need=REF_NEED), rl)
    _dirty()


def grant(uid: str, days: int, why: str, lang: str) -> bool:
    """Give `days` of Pro. Returns True if the user was told (they must have started the bot)."""
    t = TXT[lang]
    pc = pro.cfg()["pro"]
    g = G()
    if not pc:
        g["pending"].setdefault(uid, []).append({"days": days, "why": why, "lang": lang})
        _say(uid, t["gift_wait"].format(why=why))
        _dirty()
        return uid in g["users"]
    m = pro.S["members"].get(uid)
    if m and m.get("exp", 0) > time.time():
        with pro._lock:
            m["exp"] += days * DAY
        pro.backup()
        return _say(uid, t["gift_ext"].format(why=why, days=days))
    try:
        link = tb.call("createChatInviteLink", chat_id=pc, name=f"gift-{uid}-{days}"[:32], member_limit=1,
                       expire_date=int(time.time()) + 14 * DAY)["invite_link"]
    except Exception as e:
        _rt["last_error"] = f"gift link: {e}"[:150]
        g["pending"].setdefault(uid, []).append({"days": days, "why": why, "lang": lang})
        _dirty()
        return False
    ok = _say(uid, t["gift"].format(why=why, days=days, link=link))
    if not ok:   # they never opened the bot: keep it until they press Start
        g["pending"].setdefault(uid, []).append({"days": days, "why": why, "lang": lang, "link": link})
    try:
        tb.call("sendMessage", chat_id=tb.cfg()["admin"], text=f"🎁 جایزهٔ Pro ({days} روز) داده شد: {why}")
    except Exception:
        pass
    _dirty()
    return ok


def deliver_pending(uid: str):
    g = G()
    items = g["pending"].pop(uid, [])
    for it in items:
        if it.get("link"):
            _say(uid, TXT[it["lang"]]["gift"].format(why=it["why"], days=it["days"], link=it["link"]))
        else:
            grant(uid, it["days"], it["why"], it["lang"])
    if items:
        _dirty()


def _say(uid, text) -> bool:
    try:
        tb.call("sendMessage", chat_id=uid, text=text, disable_web_page_preview=True)
        return True
    except Exception:
        return False


# ------------------------------------------------------------------ loop
def tick():
    """Called every minute by the agent loop."""
    if not tb.ready() or not channels():
        return
    pro.restore()
    try:
        game_tick()
    except Exception as e:
        _rt["last_error"] = f"game: {e}"[:150]
    if _rt["dirty"] and time.time() - _rt["saved_at"] > 300:
        _rt["dirty"], _rt["saved_at"] = False, time.time()
        pro.backup()


def stats() -> dict:
    g = G()
    return {"rounds": {l: (r or {}).get("n") for l, r in g["game"].items()},
            "players": {l: len(s) for l, s in g["scores"].items()},
            "inviters": len(g["refs"]), "invited": sum(len(r["joined"]) for r in g["refs"].values()),
            "pending_prizes": len(g["pending"]), "last_error": _rt["last_error"]}
