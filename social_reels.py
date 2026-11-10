"""Create silent, vertical MP4 news reels for Instagram and TikTok.

Reels are delivered privately to the Telegram admin for review, never
automatically posted to social networks. Encoding failures do not affect
existing website or Telegram news posts.
"""
from __future__ import annotations

import io
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw
import post_card as pc

WIDTH, HEIGHT = 720, 1280
FPS = 12
SCENE_SECONDS = (4, 7, 4)


def _headline(draw, text: str, lang: str, y: int, size: int = 72) -> int:
    import social
    return social._text_block(draw, lang, 84, 996, y, text, size, pc.FG, 5)


def _scenes(poster_png: bytes, news: dict, lang: str) -> list[Image.Image]:
    poster = Image.open(io.BytesIO(poster_png)).convert("RGB")
    title = news.get("t", "") if lang == "fa" else (news.get("en_t") or news.get("t") or "")
    intro = Image.blend(poster, Image.new("RGB", poster.size, pc.BG), 0.80)
    draw = ImageDraw.Draw(intro)
    draw.rounded_rectangle((70, 240, 1010, 342), radius=26, fill=pc.BRAND)
    draw.text((110, 255), "MARKET ALERT" if lang == "en" else "CRYPTOAI  •  NEWS",
              font=pc._f(55), fill=pc.BG)
    y = _headline(draw, title, lang, 465, 77)
    sub = "خبر مهم و تأثیر احتمالی آن بر بازار" if lang == "fa" else "Breaking down the potential market impact"
    _headline(draw, sub, lang, max(1140, y + 110), 48)
    draw.text((80, 1740), "CRYPTOAI  |  15 SEC NEWS", font=pc._f(41), fill=pc.BRAND)

    outro = Image.blend(poster, Image.new("RGB", poster.size, pc.BG), 0.84)
    draw = ImageDraw.Draw(outro)
    draw.text((80, 330), "CryptoAI", font=pc._f(105), fill=pc.BRAND)
    _headline(draw, "تحلیل کامل خبر در سایت" if lang == "fa" else "FULL STORY & ANALYSIS",
              lang, 650, 77)
    _headline(draw, "برای خبرهای بیشتر دنبال کن" if lang == "fa" else "FOLLOW FOR MORE MARKET UPDATES",
              lang, 970, 60)
    draw.rounded_rectangle((75, 1370, 1005, 1510), radius=29, fill=pc.BRAND)
    draw.text((140, 1403), "SAVE  •  SHARE  •  FOLLOW", font=pc._f(52), fill=pc.BG)
    url = pc.site_url().replace("https://", "").replace("http://", "").strip("/")
    draw.text((80, 1630), (url[:42] if url else "LINK IN BIO"), font=pc._f(46), fill=pc.FG)
    draw.text((80, 1770), "News analysis • not financial advice", font=pc._f(34), fill=pc.MUTED)
    # Include the CryptoAI website and Persian/English Telegram channels in the outro.
    import social
    social.add_promo_footer(outro)
    return [im.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS) for im in (intro, poster, outro)]


def render_video(poster_png: bytes, news: dict, lang: str) -> bytes:
    """Create a 15-second H.264 MP4 with three animated scenes."""
    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise RuntimeError("Video encoder missing (install imageio-ffmpeg)") from exc
    with tempfile.TemporaryDirectory(prefix="cryptoai_reel_") as d:
        p = Path(d)
        for i, img in enumerate(_scenes(poster_png, news, lang)):
            img.save(p / f"scene{i}.png", "PNG")
        args = [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y"]
        for i, sec in enumerate(SCENE_SECONDS):
            args += ["-loop", "1", "-framerate", str(FPS), "-t", str(sec),
                     "-i", str(p / f"scene{i}.png")]
        filters = []
        for i, sec in enumerate(SCENE_SECONDS):
            motion = "min(zoom+0.0011,1.14)" if i != 1 else "min(zoom+0.0005,1.08)"
            filters.append(
                f"[{i}:v]zoompan=z='{motion}':x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2':"
                f"d=1:s={WIDTH}x{HEIGHT}:fps={FPS},trim=duration={sec},setpts=PTS-STARTPTS,"
                f"fade=t=in:st=0:d=0.35[v{i}]"
            )
        filters.append("".join(f"[v{i}]" for i in range(len(SCENE_SECONDS))) +
                       f"concat=n={len(SCENE_SECONDS)}:v=1:a=0,format=yuv420p[v]")
        output = p / "reel.mp4"
        args += ["-filter_complex", ";".join(filters), "-map", "[v]", "-an", "-c:v", "libx264",
                 "-preset", "ultrafast", "-crf", "29", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                 "-threads", "2", str(output)]
        try:
            subprocess.run(args, check=True, capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Video encoding timed out") from exc
        except subprocess.CalledProcessError as exc:
            raise RuntimeError("Video encoding failed: " + (exc.stderr or "unknown")[-240:]) from exc
        video = output.read_bytes()
        if not video or len(video) > 48 * 1024 * 1024:
            raise RuntimeError("Video file is empty or exceeds Telegram upload limit")
        return video


def send_reels(news: dict, assets: list) -> str:
    """Send review-ready Persian and English reels to Telegram admin."""
    import requests
    import social
    import telegram_bot as tb

    admin = tb.cfg()["admin"]
    if not admin:
        return "Telegram admin chat is not configured."
    completed = []
    errors = []
    for lang in ("fa", "en"):
        try:
            poster = social.compose(pc.render_card(news, assets, lang), news, lang, 1080, 1920)
            video = render_video(poster, news, lang)
            title = news.get("t") if lang == "fa" else news.get("en_t") or news.get("t")
            message = ("🎬 ریلز آماده برای اینستاگرام و تیک‌تاک (فارسی)" if lang == "fa" else
                       "🎬 Ready-to-post Instagram Reel / TikTok (English)")
            caption_lines = [message, title or "", "", *social.promo_caption(lang)]
            response = requests.post(
                tb.API.format(token=tb.cfg()["token"], method="sendVideo"),
                data={"chat_id": admin, "caption": "\n".join(caption_lines)[:1000],
                      "supports_streaming": "true"},
                files={"video": (f"cryptoai-{lang}-reel.mp4", video, "video/mp4")}, timeout=120)
            response.raise_for_status()
            if not response.json().get("ok"):
                raise RuntimeError(response.json().get("description", "Telegram rejected video"))
            completed.append(lang)
        except Exception as exc:
            errors.append(f"{lang}: {str(exc)[:150]}")
    if errors:
        tb.call("sendMessage", chat_id=admin, text="⚠️ خطای ساخت ریلز: " + " | ".join(errors))
    return ("ریلز " + ", ".join(completed) + " فرستاده شد." if completed else
            "ساخت ریلز انجام نشد: " + " | ".join(errors))


def send_latest_reels() -> str:
    import social
    news, assets = social.pick_story()
    return send_reels(news, assets) if news else "خبر مهمی در ۲۴ ساعت اخیر برای ریلز نبود."
