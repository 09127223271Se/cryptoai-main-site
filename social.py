"""
social.py — a daily ready-to-post kit for Instagram and TikTok, sent privately to the admin in Telegram.

Every day at SOCIAL_HOUR_UTC (default 16) — or on demand with /kit — the bot picks the most market-moving
story of the last 24 hours and sends, for Persian and English:
  • a square image 1080×1080 (Instagram post)
  • a vertical image 1080×1920 (Instagram story / Reels / TikTok photo post)
  • a caption with hashtags and the channel link
Images go as files so Instagram gets full quality. Nothing is posted anywhere automatically.
"""
from __future__ import annotations

import io
import os
import time
from datetime import datetime, timezone

from PIL import Image, ImageDraw, ImageFilter

import post_card as pc
import telegram_bot as tb

HOUR = int(os.environ.get("SOCIAL_HOUR_UTC", "16") or 16)
_rt = {"day": None, "last_error": None}

TAGS = {
    "fa": "#بیت_کوین #کریپتو #ارز_دیجیتال #تحلیل_بازار #طلا #دلار #اخبار_اقتصادی #بورس #CryptoAI",
    "en": "#bitcoin #crypto #cryptonews #btc #markets #gold #stockmarket #trading #CryptoAI",
}
CTA = {
    "fa": ("تحلیل کامل هر خبر، هر روز", "لینک کانال تلگرام در بیو"),
    "en": ("Every market-moving story, analysed daily", "Telegram channel link in bio"),
}


def _channel(lang):
    c = tb.cfg()
    ch = c["channel_en"] if lang == "en" else c["channel"]
    return ch if ch.startswith("@") else ""


def _canvas(w, h):
    base = Image.new("RGB", (w, h), pc.BG)
    glow = Image.new("RGB", (w, h), pc.BG)
    d = ImageDraw.Draw(glow)
    d.ellipse((int(w * .35), -int(h * .25), int(w * 1.3), int(h * .35)), fill=(14, 40, 62))
    d.ellipse((-int(w * .4), int(h * .7), int(w * .5), int(h * 1.2)), fill=(28, 24, 10))
    return Image.blend(base, glow.filter(ImageFilter.GaussianBlur(160)), 1.0)


def _text_block(d, lang, x0, x1, y, text, size, fill, max_lines):
    fa = lang == "fa" and pc.FA
    font = pc._f(size)
    if fa:
        for ln in pc._wrap(d, text, font, x1 - x0, max_lines):
            pc._rtl(d, (x1, y), ln, font, fill)
            y += int(size * 1.45)
        return y
    words, lines, cur = text.split(), [], ""
    for w_ in words:
        t_ = (cur + " " + w_).strip()
        if d.textlength(t_, font=font) <= x1 - x0:
            cur = t_
        else:
            lines.append(cur); cur = w_
    lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]; lines[-1] = lines[-1].rstrip(".,") + "…"
    for ln in lines:
        d.text((x0, y), ln, font=font, fill=fill)
        y += int(size * 1.3)
    return y


def _right(d, lang, xy, text, size, fill, bold=True):
    if lang == "fa" and pc.FA:
        pc._rtl(d, xy, text, pc._f(size, bold), fill)
    else:
        d.text(xy, text, font=pc._f(size, bold), fill=fill, anchor="ra")


def compose(card_png: bytes, n: dict, lang: str, w: int, h: int) -> bytes:
    """Put the 1280×720 card on a square or vertical canvas with a big headline and a call to action."""
    img = _canvas(w, h)
    d = ImageDraw.Draw(img)
    card = Image.open(io.BytesIO(card_png)).convert("RGB")
    cw = w - 60
    card = card.resize((cw, int(card.height * cw / card.width)), Image.LANCZOS)
    pad = 30
    d.text((pad + 10, 40), "CryptoAI", font=pc._f(64 if h > w else 54), fill=pc.BRAND)
    date = datetime.fromtimestamp(n.get("ts") or time.time(), timezone.utc).strftime("%d %b %Y")
    d.text((w - pad - 10, 60), date, font=pc._fn(34 if h > w else 30), fill=pc.MUTED, anchor="ra")
    head = n.get("t") if lang == "fa" else (n.get("en_t") or n.get("t"))
    if h > w:   # vertical: big headline, card, call to action
        y = _text_block(d, lang, pad + 10, w - pad - 10, 190, head or "", 64, pc.FG, 4)
        top = max(y + 50, 560)
        img.paste(card, (pad, top))
        y2 = top + card.height + 70
        cta, bio = CTA[lang]
        d = ImageDraw.Draw(img)
        _right(d, lang, (w - pad - 10, y2), cta, 46, pc.SIGNAL) if lang == "fa" else d.text((pad + 10, y2), cta, font=pc._f(46), fill=pc.SIGNAL)
        ch = _channel(lang)
        line = (f"Telegram: {ch}" if ch else bio)
        d.text((pad + 10, y2 + 90), line, font=pc._f(44), fill=pc.BRAND)
        if ch:
            _right(d, lang, (w - pad - 10, y2 + 170), bio, 36, pc.MUTED, False) if lang == "fa" else \
                d.text((pad + 10, y2 + 170), bio, font=pc._f(36, False), fill=pc.MUTED)
        # centre the body (headline → call to action) in the space under the header
        end = y2 + 240
        off = max(0, (h - end - 40) // 2)
        if off:
            body = img.crop((0, 150, w, end))
            bg = _canvas(w, h)
            bg.paste(img.crop((0, 0, w, 150)), (0, 0))
            bg.paste(body, (0, 150 + off))
            img = bg
    else:       # square: headline, card, channel
        y = _text_block(d, lang, pad + 10, w - pad - 10, 150, head or "", 50, pc.FG, 3)
        top = max(y + 30, 330)
        top = min(top, h - card.height - 110)
        img.paste(card, (pad, top))
        d = ImageDraw.Draw(img)
        ch = _channel(lang)
        d.text((pad + 10, h - 80), (f"Telegram: {ch}" if ch else CTA[lang][1]), font=pc._f(36), fill=pc.BRAND)
    out = io.BytesIO()
    img.save(out, "PNG", optimize=True)
    return out.getvalue()


def caption(n: dict, assets: list, lang: str) -> str:
    """Plain-text caption for Instagram/TikTok (no HTML)."""
    head = n.get("t") if lang == "fa" else (n.get("en_t") or n.get("t"))
    im = [x for x in (n.get("im") or []) if x.get("d")][:4]
    if lang == "fa":
        lines = [f"📰 {head}", "", "اثر احتمالی:"]
        for x in im:
            lines.append(f"{'🟢' if x['d'] > 0 else '🔴'} {pc.NAMES.get(x['a'], x['a'])} {'↑' if x['d'] > 0 else '↓'} {pc.STRENGTH.get(x.get('s', 1), '')}: {x.get('w', '')}")
        ch = _channel("fa")
        lines += ["", "تحلیل لحظه‌ای همهٔ خبرهای مهم بازار در کانال تلگرام ما" + (f": {ch}" if ch else " (لینک در بیو)"),
                  "⚠️ تحلیل خبر است، سیگنال خرید یا فروش نیست.", "", TAGS["fa"]]
    else:
        lines = [f"📰 {head}", "", "Likely effect:"]
        for x in im:
            lines.append(f"{'🟢' if x['d'] > 0 else '🔴'} {pc.EN.get(x['a'], x['a'])} {'↑' if x['d'] > 0 else '↓'} {pc.STRENGTH_EN.get(x.get('s', 1), '')}: {x.get('we', '')}")
        ch = _channel("en")
        lines += ["", "Live analysis of every market-moving story on our Telegram channel" + (f": {ch}" if ch else " (link in bio)"),
                  "⚠️ News analysis, not a buy/sell signal.", "", TAGS["en"]]
    return "\n".join(lines)


def _send_file(chat, png: bytes, name: str, cap: str = ""):
    import requests
    c = tb.cfg()
    r = requests.post(tb.API.format(token=c["token"], method="sendDocument"),
                      data={"chat_id": str(chat), "caption": cap[:1024], "disable_notification": "true"},
                      files={"document": (name, png, "image/png")}, timeout=60)
    if not r.json().get("ok"):
        raise RuntimeError(r.text[:200])


# ------------------------------------------------------------------ Instagram auto-publishing
# Instagram API with Instagram Login (professional account, no Facebook Page needed).
# Render: INSTAGRAM_TOKEN = long-lived Instagram user access token (instagram_business_basic +
# instagram_business_content_publish). The token is refreshed automatically before it expires (60 days)
# and the fresh one is kept in the pinned backup. INSTAGRAM_AUTO=0 turns auto-posting off.
IG = "https://graph.instagram.com/v22.0"
_media: dict = {}          # one-time public image files for Meta to fetch: key -> (jpeg bytes, expires)


def media_get(key: str):
    item = _media.get(key)
    if not item or item[1] < time.time():
        return None
    return item[0]


def _host(png: bytes) -> str:
    """Serve a JPEG at a public URL for one hour (Instagram fetches images by URL, JPEG only)."""
    import secrets
    im = Image.open(io.BytesIO(png)).convert("RGB")
    out = io.BytesIO()
    im.save(out, "JPEG", quality=92)
    key = secrets.token_urlsafe(16)
    for k in [k for k, v in _media.items() if v[1] < time.time()]:
        _media.pop(k, None)
    _media[key] = (out.getvalue(), time.time() + 3600)
    return f"{pc.site_url()}/social/media/{key}.jpg"


def ig_token() -> str:
    import pro
    return (pro.S.get("ig_token") or os.environ.get("INSTAGRAM_TOKEN", "")).strip()


def ig_ready() -> bool:
    return bool(ig_token()) and bool(pc.site_url()) and os.environ.get("INSTAGRAM_AUTO", "1") != "0"


def _ig(method, path, **params):
    import requests
    params["access_token"] = ig_token()
    r = (requests.post if method == "POST" else requests.get)(f"{IG}/{path}", params=params, timeout=60)
    j = r.json()
    if "error" in j:
        raise RuntimeError(j["error"].get("message", str(j["error"]))[:200])
    return j


def ig_refresh():
    """Long-lived tokens last 60 days; refresh once a week so it never runs out."""
    import pro
    import requests
    if not ig_token() or time.time() - pro.S.get("ig_refreshed", 0) < 7 * 24 * 3600:
        return
    try:
        r = requests.get("https://graph.instagram.com/refresh_access_token",
                         params={"grant_type": "ig_refresh_token", "access_token": ig_token()}, timeout=30).json()
        if r.get("access_token"):
            pro.S["ig_token"], pro.S["ig_refreshed"] = r["access_token"], time.time()
            pro.backup()
    except Exception as e:
        _rt["last_error"] = f"ig refresh: {e}"[:150]


def ig_publish(png: bytes, caption_text: str = "", story: bool = False) -> str:
    params = {"image_url": _host(png)}
    if story:
        params["media_type"] = "STORIES"
    else:
        params["caption"] = caption_text[:2200]
    cid = _ig("POST", "me/media", **params)["id"]
    for _ in range(20):               # wait until Instagram has processed the image
        st = _ig("GET", cid, fields="status_code").get("status_code")
        if st in (None, "FINISHED"):
            break
        if st == "ERROR":
            raise RuntimeError("instagram could not process the image")
        time.sleep(3)
    return _ig("POST", "me/media_publish", creation_id=cid)["id"]


def instagram_daily(n: dict, assets: list) -> str:
    lang = os.environ.get("INSTAGRAM_LANG", "fa")
    card = pc.render_card(n, assets, lang)
    done = []
    try:
        ig_publish(compose(card, n, lang, 1080, 1080), caption(n, assets, lang))
        done.append("پست")
    except Exception as e:
        _rt["last_error"] = f"ig post: {e}"[:150]
    try:
        ig_publish(compose(card, n, lang, 1080, 1920), story=True)
        done.append("استوری")
    except Exception as e:
        _rt["last_error"] = f"ig story: {e}"[:150]
    return " و ".join(done)


def pick_story():
    import news_live
    b = news_live.get_brief()
    feed, assets = b.get("feed") or [], b.get("assets") or []
    now = time.time()
    cand = [x for x in feed if now - (x.get("ts") or 0) < 24 * 3600 and [i for i in x.get("im") or [] if i.get("d")]]
    cand.sort(key=lambda x: (-(x.get("imp") or 1), -len(x.get("im") or []), -(x.get("ts") or 0)))
    return (cand[0] if cand else None), assets


def send_kit() -> str:
    n, assets = pick_story()
    if not n:
        return "خبر مهمی در ۲۴ ساعت اخیر برای بستهٔ شبکه‌های اجتماعی نبود."
    admin = tb.cfg()["admin"]
    ig_note = ""
    if ig_ready():
        posted = instagram_daily(n, assets)
        ig_note = (f"✅ اینستاگرام خودکار: {posted} منتشر شد.\n" if posted else
                   f"⚠️ انتشار خودکار اینستاگرام نشد: {_rt['last_error']}\n")
    tb.call("sendMessage", chat_id=admin, text=ig_note + "📲 بستهٔ امروز (فارسی و انگلیسی) برای تیک‌تاک و هر جای دیگر؛ کپشن زیر هر بسته است.")
    for lang in ("fa", "en"):
        card = pc.render_card(n, assets, lang)
        _send_file(admin, compose(card, n, lang, 1080, 1080), f"cryptoai-{lang}-post-1080x1080.png", "Instagram post" if lang == "en" else "پست اینستاگرام (مربعی)")
        _send_file(admin, compose(card, n, lang, 1080, 1920), f"cryptoai-{lang}-story-1080x1920.png", "Story / Reels / TikTok" if lang == "en" else "استوری، ریلز و تیک‌تاک (عمودی)")
        tb.call("sendMessage", chat_id=admin, text=caption(n, assets, lang), disable_web_page_preview=True)
    return "بستهٔ شبکه‌های اجتماعی فرستاده شد."


def tick():
    if not tb.ready():
        return
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    if now.hour == HOUR and _rt["day"] != today:
        _rt["day"] = today
        try:
            send_kit()
        except Exception as e:
            _rt["last_error"] = str(e)[:150]
    if now.minute == 7:
        ig_refresh()


def status() -> dict:
    return {"instagram": ig_ready(), "last_error": _rt["last_error"]}
