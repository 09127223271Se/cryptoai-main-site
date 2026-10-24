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


_mcache: dict = {}


def _candles(sym):
    try:
        import trader_engine
        cs = trader_engine.fetch_candles(sym, "1h", 240)
        return cs
    except Exception:
        return None


def market_state(sym="BTC", news_score: int = 0) -> dict | None:
    """Technical picture (trader engine) + Monte Carlo 24h range + today's news pressure → one outlook.
    Cached 60 s. Never an entry point: it says where the market is, which way the evidence leans
    and how far it can plausibly move, with probabilities."""
    key = (sym, news_score)
    c = _mcache.get(key)
    if c and time.time() - c["at"] < 60:
        return c["v"]
    cs = _candles(sym)
    if not cs or len(cs["c"]) < 180:
        return None
    import trader_engine as te
    a = te.analyze(sym, cs)
    sim = te.simulate(a, horizon=24, paths=4000, seed=7)
    k = [(float(cs["t"][i]) / 1000, float(cs["o"][i]), float(cs["h"][i]), float(cs["l"][i]), float(cs["c"][i]))
         for i in range(len(cs["c"]) - 72, len(cs["c"]))]
    tech = a["bias"]                                   # -1 / 0 / +1 from trend + patterns
    news = 1 if news_score >= 12 else -1 if news_score <= -12 else 0
    if tech and news and tech == news:
        verdict, lean = ("up_strong" if tech > 0 else "down_strong"), tech
    elif tech and news and tech != news:
        verdict, lean = "conflict", 0
    elif tech or news:
        lean = tech or news
        verdict = "up" if lean > 0 else "down"
    else:
        verdict, lean = "range", 0
    v = {"sym": sym, "candles": k, "price": a["last"], "ch24": a["chg24h"] * 100,
         "res": a["res"], "sup": a["sup"], "week_high": a["week_high"], "week_low": a["week_low"],
         "rsi": a["rsi"], "trend": "up" if a["trend"] > 0 else "down" if a["trend"] < 0 else "range",
         "tags": [t["fa"] for t in a["tags"]], "tech": tech, "news": news, "news_score": news_score,
         "verdict": verdict, "lean": lean,
         "p05": sim["p05"], "p25": sim["p25"], "p50": sim["median"], "p75": sim["p75"], "p95": sim["p95"],
         "touch_res": sim["touch"]["resistance"]["prob"], "touch_sup": sim["touch"]["support"]["prob"]}
    _mcache[key] = {"at": time.time(), "v": v}
    return v


VERDICT_FA = {"up_strong": "صعودی (تکنیکال و خبر هم‌جهت)", "down_strong": "نزولی (تکنیکال و خبر هم‌جهت)",
              "up": "متمایل به صعود", "down": "متمایل به نزول", "conflict": "متضاد: چارت و خبر خلاف هم‌اند",
              "range": "بدون جهت روشن (نوسانی)"}
VERDICT_SHORT = {"up_strong": "صعودی قوی", "down_strong": "نزولی قوی", "up": "متمایل به صعود",
                 "down": "متمایل به نزول", "conflict": "چارت و خبر متضاد", "range": "نوسانی"}


def outlook_text(ms: dict) -> list[str]:
    """Persian lines for the caption."""
    name = NAMES.get(ms["sym"], ms["sym"])
    tf = {"up": "صعودی", "down": "نزولی", "range": "خنثی"}[ms["trend"]]
    nf = "صعودی" if ms["news"] > 0 else "نزولی" if ms["news"] < 0 else "خنثی"
    out = [f"🎯 <b>وضعیت {name}:</b> {_money(ms['price'])} ({'+' if ms['ch24'] >= 0 else ''}{ms['ch24']:.1f}٪ در ۲۴ ساعت)",
           f"• روند ساعتی چارت: {tf}" + (f" · {'، '.join(ms['tags'][:2])}" if ms["tags"] else ""),
           f"• فشار خبری: {nf}",
           f"• جمع‌بندی: <b>{VERDICT_FA[ms['verdict']]}</b>",
           f"• مقاومت نزدیک {_money(ms['res'])} (احتمال لمس در ۲۴ ساعت {ms['touch_res'] * 100:.0f}٪) · "
           f"حمایت نزدیک {_money(ms['sup'])} ({ms['touch_sup'] * 100:.0f}٪)",
           f"• محدودهٔ محتمل ۲۴ ساعت آینده: {_money(ms['p25'])} تا {_money(ms['p75'])} (۵۰٪) · "
           f"{_money(ms['p05'])} تا {_money(ms['p95'])} (۹۰٪)"]
    return out


def _money(v):
    return f"${v:,.0f}" if v >= 100 else f"${v:,.2f}"




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

    # left: price chart (the coin this news moves most; Bitcoin by default) + 24h probable range
    cx0, cy0, cx1, cy1 = 40, y, 610, 600
    _rr(d, (cx0, cy0, cx1, cy1), 18, fill=PANEL, outline=LINE)
    sym = "ETH" if any(x.get("a") == "ETH" and x.get("s", 1) > max([i.get("s", 1) for i in n.get("im") or [] if i.get("a") == "BTC"] or [0])
                       for x in n.get("im") or []) else "BTC"
    score = {a["key"]: a["score"] for a in assets}
    ms = market_state(sym, score.get(sym, 0)) or (market_state("BTC", score.get("BTC", 0)) if sym != "BTC" else None)
    if ms:
        k = ms["candles"]
        vals = [x[2] for x in k] + [x[3] for x in k] + [ms["p05"], ms["p95"], ms["res"], ms["sup"]]
        lo, hi = min(vals), max(vals)
        pad = (hi - lo) * .06 or 1
        lo_s, hi_s = lo - pad, hi + pad
        px0, pxk, pxz, py0, py1 = cx0 + 22, cx1 - 190, cx1 - 110, cy0 + 100, cy1 - 24
        step = (pxk - px0) / len(k)
        Y = lambda v: py1 - (v - lo_s) / (hi_s - lo_s) * (py1 - py0)
        for gy in range(4):
            yy = py0 + gy * (py1 - py0) / 3
            d.line((px0, yy, pxz, yy), fill=LINE, width=1)
        # 24h probable range: 90% band, 50% band, median
        zone = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        zd = ImageDraw.Draw(zone)
        zc = UP if ms["lean"] > 0 else DOWN if ms["lean"] < 0 else BRAND
        zd.polygon([(pxk + 4, Y(ms["price"])), (pxz, Y(ms["p95"])), (pxz, Y(ms["p05"]))], fill=zc + (40,))
        zd.polygon([(pxk + 4, Y(ms["price"])), (pxz, Y(ms["p75"])), (pxz, Y(ms["p25"]))], fill=zc + (90,))
        img.paste(zone, (0, 0), zone)
        d = ImageDraw.Draw(img)
        d.line((pxk + 4, Y(ms["price"]), pxz, Y(ms["p50"])), fill=zc, width=2)
        if FA:
            _rtl(d, (pxz, py1 + 2), "۲۴ ساعت آینده", _f(13, False), MUTED)
        # resistance and support
        for lvl, col_l, lab in ((ms["res"], DOWN, "مقاومت"), (ms["sup"], UP, "حمایت")):
            yy = Y(lvl)
            for xx in range(int(px0), int(pxz), 14):
                d.line((xx, yy, xx + 8, yy), fill=col_l, width=2)
            d.text((pxz + 8, yy - 22), _money(lvl), font=_fn(16), fill=col_l)
            if FA:
                _rtl(d, (cx1 - 14, yy + 1), lab, _f(14, False), col_l)
        # candles
        for i, (t, o, h_, l_, c) in enumerate(k):
            x = px0 + i * step + step / 2
            col_c = UP if c >= o else DOWN
            d.line((x, Y(h_), x, Y(l_)), fill=col_c, width=1)
            top, bot = Y(max(o, c)), Y(min(o, c))
            d.rectangle((x - step * .36, top, x + step * .36, max(bot, top + 1)), fill=col_c)
        # the news moment
        nt = n.get("ts") or 0
        if k[0][0] < nt <= k[-1][0] + 3600:
            i = min(len(k) - 1, int((nt - k[0][0]) // 3600))
            x = px0 + i * step + step / 2
            for yy in range(int(py0), int(py1), 12):
                d.line((x, yy, x, yy + 6), fill=SIGNAL, width=2)
            if FA:
                _rtl(d, (x - 6, py0 - 22), "زمان خبر", _f(15), SIGNAL)
        # header: coin, price, 24h, combined verdict
        col = UP if ms["ch24"] >= 0 else DOWN
        d.text((cx0 + 22, cy0 + 14), f"{ms['sym']} · 72h", font=_f(19, False), fill=MUTED)
        d.text((cx0 + 22, cy0 + 38), _money(ms["price"]), font=_fn(30), fill=FG)
        pw = d.textlength(_money(ms["price"]), font=_fn(30))
        d.text((cx0 + 34 + pw, cy0 + 48), f"{'+' if ms['ch24'] >= 0 else ''}{ms['ch24']:.2f}% 24h", font=_fn(19), fill=col)
        if FA:
            vl = VERDICT_SHORT[ms["verdict"]]
            vcol = UP if ms["lean"] > 0 else DOWN if ms["lean"] < 0 else (SIGNAL if ms["verdict"] == "conflict" else FLAT)
            tw = _len(d, vl, _f(18))
            _rr(d, (cx1 - 22 - tw - 26, cy0 + 16, cx1 - 22, cy0 + 52), 18, outline=vcol, width=2)
            _rtl(d, (cx1 - 35, cy0 + 21), vl, _f(18), vcol)
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
    ms = market_state("BTC", next((a["score"] for a in assets if a["key"] == "BTC"), 0))
    chart = (f"BTC {ms['price']:.0f}, hourly trend {ms['trend']}, patterns {ms['tags']}, RSI {ms['rsi']:.0f}, "
             f"resistance {ms['res']:.0f}, support {ms['sup']:.0f}, combined view {ms['verdict']}") if ms else "n/a"
    prompt = ("Write 2 short Persian sentences (max 45 words) for a Telegram crypto channel. Match the news with the chart: "
              "does the news support or contradict what the chart shows, and which level (resistance or support) matters next "
              "and what to watch (a data release, the dollar, yields). Educational tone. NO buy/sell advice, NO entry points, "
              "NO stop-loss. Output only the sentences.\n"
              f"NEWS: {n.get('t')} — {n.get('b')}\nEFFECTS: {im}\nTODAY'S NEWS PRESSURE: {press}\nCHART: {chart}")
    try:
        return ai_client.ask(prompt, max_tokens=300, timeout=40).strip().strip('"')
    except Exception:
        return ""


def caption(n: dict, assets: list, with_take: bool = True) -> str:
    e = html.escape
    head = ("🚨 <b>خبر فوری بازار</b>" if n.get("imp", 1) >= 3 else "📰 <b>تحلیل خبر</b>") + \
           (f" · {e(n['city'])}" if n.get("city") else "")
    im = [x for x in (n.get("im") or []) if x.get("d")]

    score = {a["key"]: a["score"] for a in assets}
    ms = market_state("BTC", score.get("BTC", 0))
    full = outlook_text(ms) if ms else []

    def build(reason_len, body_len, take, look):
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
        if look:
            parts += [""] + look
        parts += ["", f"<i>منبع: {e(n['source']['name'])}</i>", DISCLAIMER]
        return "\n".join(parts)

    take = _take(n, assets) if with_take else ""
    short = [full[0], full[3], full[4], full[5]] if full else []
    c = ""
    for rl, bl, tk, lk in ((90, 220, take, full), (70, 160, take, full), (60, 0, take, full), (60, 0, take, short),
                           (50, 0, "", short), (0, 0, "", short), (0, 0, "", [])):
        c = build(rl, bl, tk, lk)
        if len(c) <= 1024:      # Telegram photo captions: 1024 characters
            return c
    return c


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
