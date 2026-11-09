"""
social.py — a daily ready-to-post kit for Instagram and TikTok, sent privately to the admin in Telegram.

Every day at SOCIAL_HOUR_UTC (default 16) — or on demand with /kit — the bot picks the most market-moving
story of the last 24 hours and sends, for Persian and English:
  • a square image 1080×1080 (Instagram post)
  • a vertical image 1080×1920 (Instagram story / Reels / TikTok photo post)
  • a caption with hashtags and the channel link
Purpose: attract followers with sourced news, then direct them to the matching-language website and Telegram channel.
Images go privately to the admin as full-quality files for manual publication.
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



def _clean(text, lang):
    text = str(text or "").strip()
    return pc._no_fa(text) if lang == "en" else text


def _short(text, limit):
    text = str(text or "").strip()
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


def _destinations(lang):
    from urllib.parse import urlencode, urlsplit, urlunsplit
    base = pc.site_url()
    site = ""
    if base:
        parts = urlsplit(base)
        path = parts.path.rstrip("/") + ("/en/trader" if lang == "en" else "/trader")
        site = urlunsplit((parts.scheme, parts.netloc, path,
                          urlencode({"utm_source": "social", "utm_medium": "organic",
                                     "utm_campaign": "daily_news", "utm_content": lang}), ""))
    explicit = os.environ.get("PUBLIC_CHANNEL_URL_EN" if lang == "en" else "PUBLIC_CHANNEL_URL", "").strip()
    channel = explicit if explicit.startswith("https://t.me/") else ""
    if not channel and _channel(lang):
        channel = "https://t.me/" + _channel(lang)[1:]
    return site, channel


def compose(card_png: bytes, n: dict, lang: str, w: int, h: int) -> bytes:
    """News-first promotional artwork. No invented prices, dominance or charts."""
    fa = lang == "fa"
    title = _clean(n.get("t") if fa else n.get("en_t"), lang)
    if not title:
        raise ValueError("A verified headline in the selected language is required")
    img = _canvas(w, h)
    d = ImageDraw.Draw(img)
    cyan, purple, gold = (56, 220, 255), (181, 98, 255), (255, 204, 99)
    left, right = 72, w - 130
    vertical = h > w
    top = 160 if vertical else 70
    d.rounded_rectangle((36, 36, w - 36, h - 36), 32, outline=purple, width=2)
    d.text((left, top), "CryptoAI", font=pc._f(42), fill=cyan)
    stamp = datetime.fromtimestamp(n.get("ts") or time.time(), timezone.utc).strftime("%d %b · %H:%M UTC")
    d.text((left, top + 58), stamp, font=pc._fn(24), fill=pc.MUTED)
    impacts = [x for x in (n.get("im") or []) if x.get("d")]
    symbols = list(dict.fromkeys(str(x.get("a")) for x in impacts if x.get("a")))
    symbol = symbols[0] if symbols else "MARKETS"
    symbol = symbol if symbol in pc.EN else "MARKETS"
    d.text((left, top + 125), symbol, font=pc._f(116 if vertical else 88),
           fill=gold if symbol == "BTC" else cyan)
    y = top + (290 if vertical else 245)
    hook = "این خبر چرا مهم است؟" if fa else "WHY THIS NEWS MATTERS"
    y = _text_block(d, lang, left, right, y, hook, 36, purple, 1)
    y += 30
    y = _text_block(d, lang, left, right, y, _short(title, 150),
                    54 if vertical else 44, pc.FG, 4 if vertical else 3)
    y += 32
    if vertical:
        body = _clean(n.get("b") if fa else n.get("en_b"), lang)
        if body:
            y = _text_block(d, lang, left, right, y, _short(body, 200), 32, pc.MUTED, 4)
            y += 35
        for item in impacts[:2]:
            name = (pc.NAMES if fa else pc.EN).get(item.get("a"), "")
            reason = _clean(item.get("w") if fa else item.get("we"), lang)
            if not name or not reason:
                continue
            label = ("اثر احتمالی: " if fa else "Possible effect: ") + name
            y = _text_block(d, lang, left, right, y, label, 30, cyan, 1)
            y = _text_block(d, lang, left, right, y + 8, _short(reason, 100), 28, pc.FG, 2)
            y += 20
    footer = h - (420 if vertical else 210)
    d.line((left, footer, right, footer), fill=purple, width=2)
    _text_block(d, lang, left, right, footer + 20,
                "برای خبرهای مهم بازار فالو کن" if fa else "FOLLOW FOR MARKET CONTEXT",
                32, cyan, 1)
    _text_block(d, lang, left, right, footer + 75,
                "تحلیل کامل در سایت و تلگرام" if fa else "FULL ANALYSIS · SITE + TELEGRAM",
                28, pc.FG, 1)
    _text_block(d, lang, left, right, footer + 120,
                "لینک‌ها در بیو" if fa else "LINKS IN BIO", 26, gold, 1)
    if vertical:
        source = _clean((n.get("source") or {}).get("name"), lang)
        _text_block(d, lang, left, right, footer + 175,
                    ("منبع: " if fa else "Source: ") + source, 22, pc.MUTED, 1)
        _text_block(d, lang, left, right, footer + 220,
                    "تحلیل خبری؛ نه سیگنال معامله" if fa else "News analysis, not a trade signal",
                    22, pc.MUTED, 1)
    out = io.BytesIO()
    img.save(out, "PNG", optimize=True)
    return out.getvalue()


def caption(n: dict, assets: list, lang: str) -> str:
    fa = lang == "fa"
    title = _clean(n.get("t") if fa else n.get("en_t"), lang)
    body = _clean(n.get("b") if fa else n.get("en_b"), lang)
    lines = [title, "", _short(body, 400)]
    impacts = [x for x in (n.get("im") or []) if x.get("d")]
    for item in impacts[:3]:
        name = (pc.NAMES if fa else pc.EN).get(item.get("a"), "")
        reason = _clean(item.get("w") if fa else item.get("we"), lang)
        if name and reason:
            lines.append(("اثر احتمالی بر " if fa else "Possible effect on ") + name + ": " + _short(reason, 150))
    lines += ["", "کدام بخش این خبر را مهم‌تر می‌دانی؟" if fa else "Which part of this news matters most to you?",
              "برای خبرهای مهم بازار فالو کن؛ این پست را برای بررسی بعدی ذخیره کن." if fa else
              "Follow for market context. Save this post to revisit the story.",
              "تحلیل کامل در سایت و خبرهای تازه در تلگرام — لینک‌ها در بیو." if fa else
              "Full analysis on our site and fresh news on Telegram — links in bio."]
    site, channel = _destinations(lang)
    if site:
        lines += ["", ("سایت: " if fa else "Website: ") + site]
    if channel:
        lines += [("تلگرام: " if fa else "Telegram: ") + channel]
    source = n.get("source") or {}
    source_name = _clean(source.get("name"), lang)
    source_url = str(source.get("url") or "")
    if source_url.startswith(("https://", "http://")):
        lines += ["", ("منبع: " if fa else "Source: ") + source_name, source_url]
    symbols = list(dict.fromkeys(x.get("a") for x in impacts if x.get("a") in ("BTC", "ETH", "GOLD", "OIL")))
    tags = " ".join("#" + x for x in symbols[:3])
    lines += ["", "تحلیل خبری است، نه سیگنال خریدوفروش." if fa else "News analysis, not a buy/sell signal.",
              "#CryptoAI " + tags + (" #اخبار_بازار" if fa else " #MarketNews")]
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
    tb.call("sendMessage", chat_id=admin, text="📲 بستهٔ تبلیغاتی خبر برای انتشار دستی؛ لینک سایت و تلگرام هر زبان در کپشن است. این خروجی تصویر است، نه ویدیو.")
    for lang in ("fa", "en"):
        if not _clean(n.get("t") if lang == "fa" else n.get("en_t"), lang):
            continue
        card = b""
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
