# CryptoAI Main Site — سایت یکپارچه

یک سایت با یک منو برای همهٔ بخش‌ها:

| مسیر | بخش | کار |
|---|---|---|
| `/` | کره رادیو | کرهٔ زمین با ایستگاه‌های کریپتو در شهرهای دنیا، پخش صوتی خبرها، نکته‌های هوش مصنوعی دربارهٔ اثر خبر روی بازار |
| `/trader` | تریدر | اسکنر چارت ۲۴ کوین، برگهٔ ستاپ، شبیه‌سازی ۱۰٬۰۰۰ مسیر، پست تلگرام و ارسال برای تأیید |
| `/analysis` | تحلیل کریپتو | تحلیل خبر + پست سه‌زبانه (فارسی، انگلیسی، عربی) |
| `/sales` | پیدا کردن مشتری | پروفایل مشتری، جای پیدا کردنشان و پیام شخصی‌سازی‌شده (ارسال فقط با تأیید شما) |

قانون پروژه در همهٔ بخش‌ها رعایت شده: **بدون نقطهٔ ورود و بدون سیگنال خرید/فروش.**

## ساختار

```
app.py              مسیرهای صفحات و API
ai_client.py        اتصال به هوش مصنوعی (Groq یا Claude، با کلید روی سرور)
trader_engine.py    دادهٔ زندهٔ Binance، الگوها، مونت‌کارلو، ارسال به ربات تلگرام
build_static.py     ساخت نسخهٔ استاتیک (پیش‌نمایش بدون سرور) در پوشهٔ dist/
templates/          base.html (منو و قالب مشترک) + چهار صفحه
static/css/         main.css (مشترک)، radio.css، trader.css
static/js/          ai.js (اتصال مشترک به AI)، radio.js، trader.js
static/data/stations.json   ایستگاه‌ها، خبرها و نکته‌ها (به‌روز تا ۲ آبان ۱۴۰۵)
```

## API

- `GET  /api/health` — وضعیت سرور، AI و تلگرام
- `GET  /api/ai/status` و `POST /api/ai` — هوش مصنوعی سایت
- `GET  /api/stations` — داده‌های کرهٔ رادیو
- `GET  /api/trader/candles?symbols=BTC,ETH&interval=1h&limit=240` — کندل زندهٔ Binance (۶۰ ثانیه کش)
- `GET  /api/trader/scan` و `GET /api/trader/setup/<COIN>` — اسکن و ستاپ از سمت سرور
- `POST /api/trader/send` — ارسال پست به ربات برای تأیید (دکمهٔ تأیید/رد)
- `POST /api/analyze` و `POST /api/prospect` — اگر پوشهٔ crypto-business کنار سایت باشد از crewهای آن استفاده می‌شود؛ اگر نباشد صفحه‌ها خودکار از AI سایت استفاده می‌کنند.

## تنظیمات (فقط روی سرور، هیچ‌وقت داخل کد یا چت)

| متغیر | برای |
|---|---|
| `GROQ_API_KEY` | هوش مصنوعی (یا `ANTHROPIC_API_KEY`) |
| `GROQ_MODEL` | اختیاری؛ پیش‌فرض `llama-3.3-70b-versatile` |
| `TELEGRAM_BOT_TOKEN` | ربات تلگرام |
| `TELEGRAM_ADMIN_CHAT` | شناسهٔ چت کسی که پست‌ها را تأیید می‌کند |

اگر `crypto-business/.env` کنار این پوشه باشد، کلیدهای آن هم خوانده می‌شود.

## اجرا روی سرور آنلاین (بدون نصب روی کامپیوتر)

برای سرویس‌هایی مثل Render یا Railway:

- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120` (در `Procfile` هم هست)
- متغیرهای جدول بالا را در بخش Environment سرویس وارد کنید.

## نسخهٔ استاتیک

`python build_static.py` پوشهٔ `dist/` را می‌سازد. در این حالت تریدر با دادهٔ نمونه یا CSV کار می‌کند و هوش مصنوعی فقط در پیش‌نمایش claude.ai (Claude) فعال است.
