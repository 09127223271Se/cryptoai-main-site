"""
social.py — a daily ready-to-post kit for Instagram and TikTok, sent privately to the admin in Telegram.

Every day around 19:30 Europe/Stockholm — or on demand with /kit — the bot picks the most market-moving
story of the last 24 hours and sends, for Persian and English:
  • a square image 1080×1080 (Instagram post)
  • a vertical image 1080×1920 (Instagram story / Reels / TikTok photo post)
  • a caption with hashtags and the channel link
Images go as files so Instagram gets full quality. Nothing is posted anywhere automatically.
"""
from __future__ import annotations

import io
import os
import threading
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFilter

import post_card as pc
import telegram_bot as tb

SOCIAL_TZ = ZoneInfo("Europe/Stockholm")
_rt = {"day": None, "last_error": None}
_tick_lock = threading.Lock()


def _scheduled_time():
    """HH:MM in Europe/Stockholm; handles local daylight-saving changes."""
    try:
        hh, mm = map(int, os.environ.get("SOCIAL_TIME_LOCAL", "19:30").split(":"))
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return hh, mm
    except (TypeError, ValueError):
        pass
    return 19, 30

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


def promo_links() -> tuple[str, str, str]:
    """Public website plus both public Telegram channels, where configured."""
    def telegram_url(lang: str) -> str:
        env_key = "PUBLIC_CHANNEL_URL_EN" if lang == "en" else "PUBLIC_CHANNEL_URL"
        provided = os.environ.get(env_key, "").strip()
        if provided.startswith("https://t.me/"):
            return provided
        handle = _channel(lang)
        return "https://t.me/" + handle.lstrip("@") if handle else ""
    return pc.site_url(), telegram_url("fa"), telegram_url("en")


def promo_caption(lang: str) -> list[str]:
    site, fa, en = promo_links()
    if lang == "fa":
        return ["🌐 سایت: " + (site or "لینک در بیو"),
                "🇮🇷 تلگرام فارسی: " + (fa or "لینک در بیو"),
                "🌍 تلگرام انگلیسی: " + (en or "لینک در بیو")]
    return ["🌐 Website: " + (site or "link in bio"),
            "🇮🇷 Persian Telegram: " + (fa or "link in bio"),
            "🌍 English Telegram: " + (en or "link in bio")]


def add_promo_footer(img: Image.Image) -> Image.Image:
    """Legible website and both channels on every export, in a compact footer."""
    w, h = img.size
    site, fa, en = promo_links()
    entries = [("WEB", site or "LINK IN BIO"),
               ("TG FA", fa or "LINK IN BIO"),
               ("TG EN", en or "LINK IN BIO")]
    overlay = ImageDraw.Draw(img)
    tall = h > w
    font_size = 34 if tall else 26
    line_height = 49 if tall else 36
    footer_height = line_height * 3 + (52 if tall else 32)
    top = h - footer_height - 15
    overlay.rounded_rectangle((24, top, w - 24, h - 15), radius=22,
                              fill=pc.PANEL, outline=pc.LINE, width=2)
    for i, (label, raw) in enumerate(entries):
        value = raw.replace("https://", "").replace("http://", "").strip("/")
        # Never let a long URL run off the right edge of the image.
        max_chars = 46 if tall else 50
        text = (label + " · " + value)[:max_chars]
        overlay.text((53, top + (30 if tall else 19) + i * line_height),
                     text, font=pc._f(font_size, False), fill=pc.BRAND if i == 0 else pc.FG)
    return img


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
    add_promo_footer(img)
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
        lines += ["", "برای تحلیل کامل و خبرهای بیشتر، سایت و کانال‌های ما را دنبال کنید:",
                  *promo_caption("fa"),
                  "⚠️ تحلیل خبر است، سیگنال خرید یا فروش نیست.", "", TAGS["fa"]]
    else:
        lines = [f"📰 {head}", "", "Likely effect:"]
        for x in im:
            lines.append(f"{'🟢' if x['d'] > 0 else '🔴'} {pc.EN.get(x['a'], x['a'])} {'↑' if x['d'] > 0 else '↓'} {pc.STRENGTH_EN.get(x.get('s', 1), '')}: {x.get('we', '')}")
        lines += ["", "For more market news and analysis, follow our website and channels:",
                  *promo_caption("en"),
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


def send_kit(publish_instagram: bool = True) -> str:
    n, assets = pick_story()
    if not n:
        return "خبر مهمی در ۲۴ ساعت اخیر برای بستهٔ شبکه‌های اجتماعی نبود."
    admin = tb.cfg()["admin"]
    ig_note = ""
    if publish_instagram and ig_ready():
        posted = instagram_daily(n, assets)
        ig_note = (f"✅ اینستاگرام خودکار: {posted} منتشر شد.\n" if posted else
                   f"⚠️ انتشار خودکار اینستاگرام نشد: {_rt['last_error']}\n")
    tb.call("sendMessage", chat_id=admin, text=ig_note + "📲 بستهٔ امروز (فارسی و انگلیسی) برای تیک‌تاک و هر جای دیگر؛ کپشن زیر هر بسته است.")
    for lang in ("fa", "en"):
        card = pc.render_card(n, assets, lang)
        _send_file(admin, compose(card, n, lang, 1080, 1080), f"cryptoai-{lang}-post-1080x1080.png", "Instagram post" if lang == "en" else "پست اینستاگرام (مربعی)")
        _send_file(admin, compose(card, n, lang, 1080, 1920), f"cryptoai-{lang}-story-1080x1920.png", "Story / Reels / TikTok" if lang == "en" else "استوری، ریلز و تیک‌تاک (عمودی)")
        tb.call("sendMessage", chat_id=admin, text=caption(n, assets, lang), disable_web_page_preview=True)
    # Add private 15-second MP4 reels without changing existing Instagram or news publishing.
    # On cheap hosts the video encoder may be unavailable; keep the image kit working.
    if os.environ.get("SOCIAL_REELS_ENABLED", "1") != "0":
        try:
            import social_reels
            social_reels.send_reels(n, assets)
        except Exception as e:
            _rt["last_error"] = f"reels: {e}"[:150]
    return "بستهٔ شبکه‌های اجتماعی فرستاده شد."


def tick():
    """One daily *private* content kit, after 19:30 Stockholm time.

    The in-process loop and an external wake-up may both invoke this.
    A lock and backed-up local date prevent double delivery on restarts.
    """
    if not tb.ready():
        return None
    now = datetime.now(SOCIAL_TZ)
    hh, mm = _scheduled_time()
    if (now.hour, now.minute) < (hh, mm):
        return None
    today = now.date().isoformat()
    if _rt["day"] == today or not _tick_lock.acquire(blocking=False):
        return None
    try:
        import pro
        pro.restore()
        if pro.S.get("social_day") == today:
            _rt["day"] = today
            return None
        # User reviews and publishes on Instagram/TikTok manually.
        # Do NOT invoke the existing Instagram auto-publish integration here.
        result = send_kit(publish_instagram=False)
        if result != "بستهٔ شبکه‌های اجتماعی فرستاده شد.":
            _rt["last_error"] = result[:150]
            return result
        _rt["day"] = today
        pro.S["social_day"] = today
        pro.backup()
        return result
    except Exception as exc:
        _rt["last_error"] = f"daily kit: {exc}"[:150]
        return None
    finally:
        _tick_lock.release()


def status() -> dict:
    import pro
    return {"instagram": ig_ready(), "last_error": _rt["last_error"],
            "schedule": os.environ.get("SOCIAL_TIME_LOCAL", "19:30") + " Europe/Stockholm",
            "last_social_day": pro.S.get("social_day") or _rt["day"]}
