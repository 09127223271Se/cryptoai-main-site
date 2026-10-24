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


def send_kit() -> str:
    import news_live
    b = news_live.get_brief()
    feed, assets = b.get("feed") or [], b.get("assets") or []
    now = time.time()
    cand = [x for x in feed if now - (x.get("ts") or 0) < 24 * 3600 and [i for i in x.get("im") or [] if i.get("d")]]
    cand.sort(key=lambda x: (-(x.get("imp") or 1), -len(x.get("im") or []), -(x.get("ts") or 0)))
    if not cand:
        return "خبر مهمی در ۲۴ ساعت اخیر برای بستهٔ شبکه‌های اجتماعی نبود."
    n = cand[0]
    admin = tb.cfg()["admin"]
    tb.call("sendMessage", chat_id=admin, text="📲 بستهٔ امروز اینستاگرام و تیک‌تاک (فارسی و انگلیسی). فایل‌ها را ذخیره و پست کنید؛ کپشن زیر هر بسته است.")
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
