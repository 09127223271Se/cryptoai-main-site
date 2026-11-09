"""desk.py — multi-agent analysis desk inspired by the Grok Bot video.
Agents discuss direction only. Never places trades, never gives entry/SL/TP numbers as signals."""
from __future__ import annotations

import time
from typing import Any


def _money(v: float | None) -> str:
    if v is None or v <= 0:
        return "—"
    return f"${v:,.0f}" if v >= 1000 else f"${v:,.2f}"


def build_desk(sym: str = "BTC") -> dict[str, Any]:
    """Run the six agents on current data and return their short opinions + final call."""
    import post_card
    import news_live
    import trader_engine as te

    sym = (sym or "BTC").upper()
    scores = {a["key"]: a["score"] for a in (news_live.get_brief().get("assets") or [])}
    key = sym if sym in ("BTC", "ETH") else "ALT"
    ms = post_card.market_state(sym, scores.get(key, 0))
    if not ms:
        return {"ok": False, "error": "no_data", "sym": sym}

    a = te.analyze(sym)  # includes volume / flow tags
    tags = a.get("tags") or []
    bias = a.get("bias", 0)
    price = ms.get("price") or a.get("last")
    res, sup = ms.get("res"), ms.get("sup")
    rsi = ms.get("rsi") or a.get("rsi")
    news_score = scores.get(key, 0)

    # --- agent voices ---
    agents = []

    # Scout
    scout_dir = "صعودی" if bias > 0 else "نزولی" if bias < 0 else "خنثی"
    agents.append({
        "id": "scout", "name": "Scout", "color": "#3b82f6",
        "fa": f"بازار {sym} رو اسکن کردم. ساختار فعلی {scout_dir} است. RSI حدود {rsi:.0f}. مقاومت {_money(res)} · حمایت {_money(sup)}.",
        "en": f"Scanned {sym}. Current structure is {'bullish' if bias > 0 else 'bearish' if bias < 0 else 'neutral'}. RSI ~{rsi:.0f}. Resistance {_money(res)} · Support {_money(sup)}."
    })

    # News
    news_lean = "مثبت" if news_score > 1 else "منفی" if news_score < -1 else "خنثی"
    agents.append({
        "id": "news", "name": "News", "color": "#f59e0b",
        "fa": f"فشار خبری روی {key} فعلاً {news_lean} است (امتیاز {news_score:+d}). خبرهای تازه می‌توانند حرکت کوتاه‌مدت را تقویت یا تضعیف کنند.",
        "en": f"News pressure on {key} is currently {'positive' if news_score > 1 else 'negative' if news_score < -1 else 'neutral'} (score {news_score:+d}). Fresh headlines can amplify or fade short-term moves."
    })

    # Charts / volume
    vol_tags = [t for t in tags if t.get("id") in ("vol_buy", "vol_sell", "candle_buy", "candle_sell", "flow_buy", "flow_sell", "rej_res", "brk_res", "def_sup", "brk_sup")]
    vol_txt_fa = vol_tags[0]["fa"] if vol_tags else "حجم و قدرت کندل فعلاً سیگنال قوی نداده"
    vol_txt_en = vol_tags[0].get("en") or vol_txt_fa if vol_tags else "Volume and candle power currently show no strong edge"
    agents.append({
        "id": "charts", "name": "Charts", "color": "#22c55e",
        "fa": f"تحلیل چارت + حجم: {vol_txt_fa}. نزدیک مقاومت/حمایت با حجم بالا به عنوان ناحیه حساس نگه داشته می‌شود.",
        "en": f"Chart + volume: {vol_txt_en}. High-volume areas near support/resistance are treated as key zones."
    })

    # Sentiment (simple from news + RSI)
    sent = "خریداران فعال‌تر" if (bias > 0 and news_score >= 0) else "فروشندگان فعال‌تر" if (bias < 0 and news_score <= 0) else "تعادل نسبی"
    agents.append({
        "id": "sentiment", "name": "Sentiment", "color": "#ec4899",
        "fa": f"حس بازار: {sent}. ترکیب ساختار و اخبار فعلاً این حس را نشان می‌دهد.",
        "en": f"Market sentiment: {'buyers more active' if (bias > 0 and news_score >= 0) else 'sellers more active' if (bias < 0 and news_score <= 0) else 'relatively balanced'}. Structure + news currently support this read."
    })

    # Skeptic — always pushes back
    skeptic_points = []
    if abs(bias) >= 1 and abs(news_score) < 2:
        skeptic_points.append("اخبار هم‌راستا با چارت نیست" if bias > 0 else "اخبار هم‌راستا با چارت نیست")
    if rsi and (rsi > 68 or rsi < 32):
        skeptic_points.append("RSI در ناحیه افراط است")
    if not vol_tags:
        skeptic_points.append("حجم تأییدی ندارد")
    if not skeptic_points:
        skeptic_points.append("احتمال فیک شکست یا برگشت ناگهانی وجود دارد")
    agents.append({
        "id": "skeptic", "name": "Skeptic", "color": "#6b7280",
        "fa": "مخالفم: " + " · ".join(skeptic_points) + ". هیچ تریدی بدون فیلتر شک نباید انجام شود.",
        "en": "Against: " + " · ".join(skeptic_points) + ". No trade should pass without skepticism."
    })

    # Chief — summary
    final = "بیاس صعودی" if bias > 0 else "بیاس نزولی" if bias < 0 else "بیاس خنثی"
    agents.append({
        "id": "chief", "name": "Chief", "color": "#111827",
        "fa": f"جمع‌بندی میز: {final} روی {sym}. این تنها تحلیل است — هیچ سفارشی زده نمی‌شود و هیچ نقطه ورود/خروجی توصیه نمی‌گردد.",
        "en": f"Desk summary: {'bullish bias' if bias > 0 else 'bearish bias' if bias < 0 else 'neutral bias'} on {sym}. Analysis only — no orders are placed and no entry/exit is recommended."
    })

    return {
        "ok": True,
        "sym": sym,
        "price": price,
        "bias": bias,
        "agents": agents,
        "updated": time.time(),
        "note_fa": "این میز فقط برای تحلیل آموزشی است. هیچ معامله‌ای انجام نمی‌شود.",
        "note_en": "This desk is for educational analysis only. No trades are executed."
    }
