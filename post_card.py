"""
post_card.py — the picture + caption for Telegram posts.

One market-moving news item becomes:
  • a 1280×720 card: Persian headline, BTC 72-hour chart with the news moment marked,
    the news' effect on each market (up/down + strength), today's news pressure per market
  • a Persian caption (HTML): headline, summary, effect on each asset with the reason,
    a short CryptoAI take, today's pressure, the source — and never an entry point or a buy/sell call.
"""
from __future__ import annotations

import html
import io
import os
import time
from datetime import datetime, timezone

from PIL import Image, ImageDraw, ImageFilter, ImageFont, features

import ai_client

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_B = os.path.join(HERE, "static", "fonts", "Vazirmatn-Bold.ttf")
FONT_R = os.path.join(HERE, "static", "fonts", "Vazirmatn-Regular.ttf")
FA = features.check("raqm")            # Persian shaping available (bundled with Pillow wheels)

W, H = 1280, 720
BG, PANEL, LINE = (5, 9, 19), (12, 19, 34), (31, 44, 68)
FG, MUTED = (230, 235, 244), (140, 153, 178)
BRAND, SIGNAL = (34, 211, 238), (255, 201, 77)
UP, DOWN, FLAT = (51, 211, 154), (255, 106, 95), (159, 178, 216)

NAMES = {"BTC": "بیت‌کوین", "ETH": "اتریوم", "ALT": "آلت‌کوین‌ها", "GOLD": "طلا", "OIL": "نفت", "SPX": "S&P 500", "DXY": "دلار"}
EN = {"BTC": "Bitcoin", "ETH": "Ethereum", "ALT": "Altcoins", "GOLD": "Gold", "OIL": "Oil", "SPX": "S&P 500", "DXY": "US Dollar"}
STRENGTH = {1: "ملایم", 2: "متوسط", 3: "قوی"}
DISCLAIMER = "⚠️ تحلیل خبر است، سیگنال خرید یا فروش و نقطهٔ ورود نیست."


def site_url() -> str:
    return (os.environ.get("PUBLIC_SITE_URL") or os.environ.get("RENDER_EXTERNAL_URL") or "").rstrip("/")


# ------------------------------------------------------------------ drawing helpers
_fonts: dict = {}


def _f(size, bold=True):
    k = (size, bold)
    if k not in _fonts:
        try:
            _fonts[k] = ImageFont.truetype(FONT_B if bold else FONT_R, size,
                                           layout_engine=ImageFont.Layout.RAQM if FA else ImageFont.Layout.BASIC)
        except Exception:
            _fonts[k] = ImageFont.load_default()
    return _fonts[k]


def _fn(size):
    """Numbers: plain left-to-right layout so '+38' never turns into '38+'."""
    k = ("n", size)
    if k not in _fonts:
        try:
            _fonts[k] = ImageFont.truetype(FONT_B, size, layout_engine=ImageFont.Layout.BASIC)
        except Exception:
            _fonts[k] = _f(size)
    return _fonts[k]


def _rtl(d, xy_right, text, font, fill):
    """Right-aligned Persian text whose right edge is at xy_right[0]."""
    if FA:
        d.text(xy_right, text, font=font, fill=fill, anchor="ra", direction="rtl", language="fa")
    else:
        d.text(xy_right, text, font=font, fill=fill, anchor="ra")


def _len(d, text, font):
    return d.textlength(text, font=font, direction="rtl" if FA else None, language="fa" if FA else None)


def _wrap(d, text, font, width, max_lines):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if _len(d, t, font) <= width:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
            if len(lines) == max_lines:
                break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if len(lines) == max_lines and " ".join(lines) != text.strip():
        while lines[-1] and _len(d, lines[-1] + "…", font) > width:
            lines[-1] = lines[-1].rsplit(" ", 1)[0] if " " in lines[-1] else lines[-1][:-1]
        lines[-1] += "…"
    return lines


def _tri(d, cx, cy, up, color, s=11):
    pts = [(cx, cy - s), (cx - s, cy + s * .7), (cx + s, cy + s * .7)] if up else \
          [(cx, cy + s), (cx - s, cy - s * .7), (cx + s, cy - s * .7)]
    d.polygon(pts, fill=color)


def _rr(d, box, r, fill=None, outline=None, width=1):
    d.rounded_rectangle(box, r, fill=fill, outline=outline, width=width)


def _btc_series():
    try:
        import trader_engine
        rows, _ = trader_engine.fetch_rows("BTC", "1h", 72)
        return [(r[0] / 1000, float(r[4])) for r in rows]
    except Exception:
        return []


# ------------------------------------------------------------------ the card
def render_card(n: dict, assets: list) -> bytes:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    # soft glow behind the headline
    glow = Image.new("RGB", (W, H), BG)
    ImageDraw.Draw(glow).ellipse((760, -380, 1560, 300), fill=(14, 40, 62))
    img = glow.filter(ImageFilter.GaussianBlur(120))
    d = ImageDraw.Draw(img)

    # top bar
    d.text((40, 26), "CryptoAI", font=_f(34), fill=BRAND)
    ts = datetime.fromtimestamp(n.get("ts") or time.time(), timezone.utc).strftime("%d %b %Y · %H:%M UTC")
    d.text((40, 72), ts, font=_f(18, False), fill=MUTED)
    urgent = n.get("imp", 1) >= 3
    if FA:
        tag = "خبر فوری بازار" if urgent else "تحلیل اثر خبر"
        tw = _len(d, tag, _f(22))
        _rr(d, (W - 40 - tw - 36, 30, W - 40, 72), 21, fill=SIGNAL if urgent else PANEL, outline=None if urgent else LINE)
        _rr(d, (W - 40 - tw - 36, 30, W - 40, 72), 21, outline=SIGNAL if urgent else BRAND, width=2)
        _rtl(d, (W - 58, 38), tag, _f(22), (26, 18, 4) if urgent else BRAND)
        if n.get("city"):
            _rtl(d, (W - 40, 84), n["city"], _f(18, False), MUTED)

    # headline
    y = 122
    if FA:
        for ln in _wrap(d, n.get("t", ""), _f(40), W - 80, 2):
            _rtl(d, (W - 40, y), ln, _f(40), FG)
            y += 58
    else:
        d.text((40, y), "Market-moving news", font=_f(40), fill=FG)
        y += 58
    y = max(y + 12, 200)

    # left: BTC chart
    cx0, cy0, cx1, cy1 = 40, y, 610, 600
    _rr(d, (cx0, cy0, cx1, cy1), 18, fill=PANEL, outline=LINE)
    ser = _btc_series()
    if len(ser) > 5:
        xs = [p[0] for p in ser]; ys = [p[1] for p in ser]
        lo, hi = min(ys), max(ys); span = (hi - lo) or 1
        px0, px1, py0, py1 = cx0 + 22, cx1 - 22, cy0 + 86, cy1 - 26
        def P(t, v):
            return (px0 + (t - xs[0]) / ((xs[-1] - xs[0]) or 1) * (px1 - px0), py1 - (v - lo) / span * (py1 - py0))
        pts = [P(t, v) for t, v in ser]
        ch = (ys[-1] / ys[-25] - 1) * 100 if len(ys) > 25 else 0
        col = UP if ch >= 0 else DOWN
        # area fill
        area = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ad = ImageDraw.Draw(area)
        ad.polygon(pts + [(pts[-1][0], py1), (pts[0][0], py1)], fill=col + (38,))
        img.paste(area, (0, 0), area)
        d = ImageDraw.Draw(img)
        for gy in range(4):
            yy = py0 + gy * (py1 - py0) / 3
            d.line((px0, yy, px1, yy), fill=LINE, width=1)
        d.line(pts, fill=col, width=4, joint="curve")
        d.ellipse((pts[-1][0] - 7, pts[-1][1] - 7, pts[-1][0] + 7, pts[-1][1] + 7), fill=col)
        # the news moment
        nt = n.get("ts") or 0
        if xs[0] < nt <= xs[-1] + 3600:
            x = P(min(nt, xs[-1]), lo)[0]
            for yy in range(int(py0), int(py1), 12):
                d.line((x, yy, x, yy + 6), fill=SIGNAL, width=2)
            lab = "زمان خبر" if FA else "news"
            if FA:
                _rtl(d, (x - 6, py0 - 4), lab, _f(16), SIGNAL)
            else:
                d.text((x + 6, py0 - 4), lab, font=_f(16), fill=SIGNAL)
        d.text((cx0 + 22, cy0 + 16), "BTC · 72h", font=_f(20, False), fill=MUTED)
        d.text((cx0 + 22, cy0 + 40), f"${ys[-1]:,.0f}", font=_f(30), fill=FG)
        pw = d.textlength(f"${ys[-1]:,.0f}", font=_f(30))
        d.text((cx0 + 34 + pw, cy0 + 50), f"{'+' if ch >= 0 else ''}{ch:.2f}% 24h", font=_f(20), fill=col)
    else:
        d.text((cx0 + 22, cy0 + 20), "BTC", font=_f(26), fill=MUTED)

    # right: impact of this news
    rx0, rx1 = 640, W - 40
    _rr(d, (rx0, y, rx1, 600), 18, fill=PANEL, outline=LINE)
    title = "اثر احتمالی این خبر" if FA else "Likely effect"
    if FA:
        _rtl(d, (rx1 - 22, y + 16), title, _f(24), BRAND)
    else:
        d.text((rx0 + 22, y + 16), title, font=_f(24), fill=BRAND)
    im = [x for x in (n.get("im") or []) if x.get("d")][:5]
    ry = y + 70
    if not im:
        msg = "اثر روشنی روی بازارها دیده نمی‌شود" if FA else "No clear effect"
        (_rtl(d, (rx1 - 22, ry), msg, _f(22, False), MUTED) if FA else d.text((rx0 + 22, ry), msg, font=_f(22, False), fill=MUTED))
    row_h = min(56, (600 - ry - 14) // max(1, len(im)))
    for x in im:
        up = x["d"] > 0
        col = UP if up else DOWN
        name = NAMES.get(x["a"], x["a"]) if FA else EN.get(x["a"], x["a"])
        if FA:
            _rtl(d, (rx1 - 60, ry + 4), name, _f(26), FG)
            _tri(d, rx1 - 34, ry + 22, up, col)
            word = ("صعودی " if up else "نزولی ") + STRENGTH.get(x.get("s", 1), "")
            _rtl(d, (rx0 + 300, ry + 8), word, _f(20, False), col)
        else:
            d.text((rx0 + 50, ry + 4), name, font=_f(26), fill=FG)
            _tri(d, rx0 + 30, ry + 22, up, col)
        # strength bars (3 segments)
        for k in range(3):
            bx = rx0 + 22 + k * 40
            _rr(d, (bx, ry + 14, bx + 32, ry + 30), 5, fill=col if k < x.get("s", 1) else LINE)
        ry += row_h

    # bottom: today's news pressure
    by = 620
    chips = [a for a in assets if a["key"] in ("BTC", "ETH", "GOLD", "OIL", "SPX", "DXY")]
    if chips:
        lab = "فشار خبری امروز:" if FA else "Today's news pressure:"
        if FA:
            _rtl(d, (W - 40, by + 6), lab, _f(20), MUTED)
            xr = W - 40 - _len(d, lab, _f(20)) - 16
        else:
            d.text((40, by + 6), lab, font=_f(20), fill=MUTED)
        xl = 40 + (0 if FA else d.textlength(lab, font=_f(20)) + 16)
        for a in chips:
            s = a["score"]
            col = UP if s >= 12 else DOWN if s <= -12 else FLAT
            num = f"{'+' if s > 0 else '−' if s < 0 else ''}{abs(s)}"
            nw = d.textlength(num, font=_fn(19))
            if FA:
                name = NAMES[a["key"]]
                tw = _len(d, name, _f(19)) + 8 + nw
                if xr - tw - 26 < 40:
                    break
                _rr(d, (xr - tw - 26, by, xr, by + 40), 20, outline=col, width=2)
                _rtl(d, (xr - 13, by + 7), name, _f(19), col)
                d.text((xr - 13 - tw, by + 7), num, font=_fn(19), fill=col)
                xr -= tw + 36
            else:
                txt = f"{a['key']} {num}"
                tw = d.textlength(txt, font=_f(19))
                _rr(d, (xl, by, xl + tw + 26, by + 40), 20, outline=col, width=2)
                d.text((xl + 13, by + 7), txt, font=_f(19), fill=col)
                xl += tw + 36

    # footer
    host = site_url().replace("https://", "").replace("http://", "") or "CryptoAI"
    d.text((40, H - 34), host, font=_f(17, False), fill=BRAND)
    foot = "تحلیل خبر است، نه سیگنال خرید یا فروش" if FA else "News analysis, not a buy/sell signal"
    if FA:
        _rtl(d, (W - 40, H - 36), foot, _f(17, False), MUTED)
    else:
        d.text((W - 40 - d.textlength(foot, font=_f(17, False)), H - 34), foot, font=_f(17, False), fill=MUTED)

    out = io.BytesIO()
    img.save(out, "PNG", optimize=True)
    return out.getvalue()


# ------------------------------------------------------------------ caption
def _take(n, assets):
    """One or two Persian sentences: what this news means in today's context. Empty if AI is down."""
    if not ai_client.provider():
        return ""
    press = ", ".join(f"{a['key']}:{a['label']}({a['score']})" for a in assets)
    im = "; ".join(f"{x['a']} {'up' if x['d'] > 0 else 'down'} ({x['w']})" for x in (n.get("im") or []) if x.get("d"))
    prompt = ("Write 2 short Persian sentences (max 45 words) for a Telegram crypto channel: what this news means for "
              "crypto traders today and what to watch next (e.g. a data release, a reaction in the dollar or yields). "
              "Educational tone. NO buy/sell advice, NO entry points, NO price targets. Output only the sentences.\n"
              f"NEWS: {n.get('t')} — {n.get('b')}\nEFFECTS: {im}\nTODAY'S NEWS PRESSURE: {press}")
    try:
        return ai_client.ask(prompt, max_tokens=300, timeout=40).strip().strip('"')
    except Exception:
        return ""


def caption(n: dict, assets: list, with_take: bool = True) -> str:
    e = html.escape
    head = ("🚨 <b>خبر فوری بازار</b>" if n.get("imp", 1) >= 3 else "📰 <b>تحلیل خبر</b>") + \
           (f" · {e(n['city'])}" if n.get("city") else "")
    im = [x for x in (n.get("im") or []) if x.get("d")]

    def build(reason_len, body_len, take):
        parts = [head, "", f"<b>{e(n.get('t', ''))}</b>"]
        if n.get("b") and body_len:
            b = n["b"] if len(n["b"]) <= body_len else n["b"][:body_len].rsplit(" ", 1)[0] + "…"
            parts += ["", e(b)]
        if im:
            parts += ["", "📊 <b>اثر احتمالی:</b>"]
            for x in im[:5]:
                w = x.get("w", "")
                if reason_len and w:
                    w = w if len(w) <= reason_len else w[:reason_len].rsplit(" ", 1)[0] + "…"
                parts.append(f"{'🟢' if x['d'] > 0 else '🔴'} {NAMES.get(x['a'], x['a'])} {'↑' if x['d'] > 0 else '↓'} "
                             f"{STRENGTH.get(x.get('s', 1), '')}" + (f": {e(w)}" if reason_len and w else ""))
        if take:
            parts += ["", f"🧠 <b>نگاه CryptoAI:</b> {e(take)}"]
        top = [a for a in assets if a["key"] in ("BTC", "GOLD", "SPX", "DXY")]
        if top:
            parts += ["", "🌡 <b>فشار خبری امروز:</b> " + " · ".join(
                f"{NAMES[a['key']]} {a['label']}" for a in top)]
        parts += ["", f"🔗 <a href=\"{e(n['source']['url'])}\">منبع: {e(n['source']['name'])}</a>", DISCLAIMER]
        return "\n".join(parts)

    take = _take(n, assets) if with_take else ""
    for rl, bl, tk in ((110, 260, take), (80, 180, take), (60, 120, take), (60, 0, take), (0, 0, take), (0, 0, "")):
        c = build(rl, bl, tk)
        if len(c) <= 1000:      # Telegram photo captions: 1024 characters
            return c
    return c[:1000]


def channel_buttons() -> dict | None:
    base = site_url()
    if not base:
        return None
    return {"inline_keyboard": [[{"text": "📊 تحلیل کامل و نمودار زنده", "url": base + "/"},
                                 {"text": "✦ هشدار فوری با Pro", "url": base + "/pro"}]]}


def pick_news(seen: set, force: bool = False):
    """The most market-moving fresh item not posted yet, plus today's asset pressure."""
    import news_live
    b = news_live.get_brief()
    feed, assets = b.get("feed") or [], b.get("assets") or []
    now = time.time()
    cand = [x for x in feed if x["source"]["url"] not in seen and now - (x.get("ts") or 0) < 6 * 3600]
    cand.sort(key=lambda x: (-(x.get("imp") or 1), -len([i for i in x.get("im") or [] if i.get("d")]), -(x.get("ts") or 0)))
    if not cand and force:
        cand = sorted(feed, key=lambda x: (-(x.get("imp") or 1), -(x.get("ts") or 0)))
    return (cand[0] if cand else None), assets
