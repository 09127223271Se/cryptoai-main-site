# CryptoAI Main Site — سایت یکپارچه

یک سایت با یک منو برای همهٔ بخش‌ها:

| مسیر | بخش | کار |
|---|---|---|
| `/` | هوش بازار | فشار خبری روی بیت‌کوین، اتریوم، آلت‌کوین‌ها، طلا، نفت، S&P 500 و دلار؛ هر خبر با برچسب اثر و «چرا؟» |
| `/radio` | کره رادیو | کرهٔ زمین با ایستگاه‌های کریپتو در شهرهای دنیا، پخش صوتی خبرها، نکته‌های هوش مصنوعی دربارهٔ اثر خبر روی بازار |
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

## دادهٔ زنده

- **قیمت لحظه‌ای:** مرورگر بازدیدکننده مستقیم به WebSocket بازار Binance وصل می‌شود (هر معامله، حدود هر ثانیه). اگر وصل نشد Coinbase، و در آخر `/api/prices` هر ۱۰ ثانیه.
- **کندل‌های تریدر:** سرور به‌ترتیب از Binance، OKX، Bybit و Coinbase می‌گیرد. اگر سرور به هیچ‌کدام نرسید، مرورگر مستقیم از Binance می‌گیرد. هر ۲ دقیقه به‌روز می‌شود.
- **خبرها (`news_live.py`):** هر ۱۰ دقیقه. کریپتو: CoinDesk، Cointelegraph، Decrypt، The Block، Bitcoin Magazine، CryptoSlate. منابع رسمی: فدرال رزرو (بیانیه‌ها و سخنرانی‌ها)، SEC، بانک مرکزی اروپا، بانک انگلستان. اقتصاد کلان: CNBC، MarketWatch، BBC Business، خبرگزاری آناتولی، Daily Sabah، SCMP (فقط خبرهای مربوط به نرخ بهره، تورم، سهام، نفت، طلا، دلار و کریپتو). اگر ترجمهٔ هوش مصنوعی نشد، Google Translate. هر خبر بر اساس کشور یا موضوعش به ایستگاه مربوط روی کره می‌رود. Groq عنوان و خلاصهٔ فارسی و نکته‌های بالا/پایین را می‌نویسد. لینک و زمان دقیق هر خبر کنارش است.
- **نوار بازار (همهٔ صفحه‌ها):** طلا لحظه‌ای (PAXG، معادل یک اونس)، نفت WTI و برنت (قراردادهای آتی از Yahoo/Stooq، تأخیر بورس حدود ۱۰ دقیقه)، ارزش کل بازار کریپتو و دامیننس BTC، ETH، USDT، USDC، استیبل‌ها و Others (CoinGecko، با CoinPaprika به‌عنوان پشتیبان).
- **ساعت:** ساعت محلی هر شهر و ساعت بازدیدکننده، ثانیه‌به‌ثانیه.

## API

- `GET  /api/health` — وضعیت سرور، AI و تلگرام
- `GET  /api/ai/status` و `POST /api/ai` — هوش مصنوعی سایت
- `GET  /api/brief` — فشار خبری هر بازار و خبرهای تحلیل‌شده
- `GET  /api/stations` — ایستگاه‌ها با خبرهای زنده
- `GET  /api/prices?symbols=BTC,ETH` — قیمت و تغییر ۲۴ ساعت
- `GET  /api/markets` — طلا، نفت، ارزش کل بازار و دامیننس‌ها
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


## دکمهٔ کانال تلگرام

`PUBLIC_CHANNEL_URL` (مثلاً `https://t.me/mychannel`) یا اگر `TELEGRAM_CHANNEL_ID` با `@` شروع شود، لینک خودکار ساخته می‌شود.

## CryptoAI Pro (اشتراک پولی)

- صفحهٔ `/pro`: مقایسهٔ رایگان و Pro، پرداخت با تتر (TRC20) یا Telegram Stars.
- Pro = کانال خصوصی تلگرام: هشدار فوری خبرهای مهم (اهمیت ۳) با تحلیل اثر، و خلاصهٔ هوشمند هر روز ساعت ۸ صبح به وقت تهران. یک نسخهٔ کوتاه همان خلاصه برای تأیید شما به کانال عمومی می‌رود.
- تتر: هر خریدار یک مبلغ یکتا (مثلاً ۹٫۳۷) می‌گیرد؛ سرور کیف پول را روی TronGrid چک می‌کند و بعد از دریافت مبلغ دقیق لینک یک‌بارمصرف کانال Pro را می‌دهد. بعد از ۳۰ روز بدون تمدید، عضو خودکار از کانال حذف می‌شود (۳ روز قبلش یادآوری می‌گیرد).
- Stars: لینک اشتراک ماهانهٔ خود تلگرام؛ تمدید و حذف را تلگرام انجام می‌دهد.
- اطلاعات مشترکان به‌صورت فایل پشتیبان در چت خصوصی مدیر با ربات سنجاق می‌شود و بعد از ری‌استارت سرور از همان‌جا برمی‌گردد.

| متغیر | برای |
|---|---|
| `TELEGRAM_PRO_CHANNEL_ID` | شناسهٔ کانال خصوصی Pro (با -100 شروع می‌شود). ربات باید در آن ادمین باشد با اجازهٔ «دعوت کاربر» و «حذف کاربر». |
| `PRO_USDT_TRC20` | آدرس کیف پول تتر شبکهٔ TRON (آدرس عمومی، نه کلید) |
| `PRO_PRICE_USDT` | قیمت ماهانه به تتر (پیش‌فرض ۹) |
| `PRO_STARS` | قیمت ماهانه به Stars (پیش‌فرض ۵۰۰) |


## English site and English channel

- English pages: `/en`, `/en/radio`, `/en/trader`, `/en/analysis`, `/en/pro`. Every page has a فارسی / English switch in the menu.
- News analysis is produced once in both languages (Persian and English titles, reasons and summaries).
- `TELEGRAM_CHANNEL_EN` (e.g. `@CryptoAI_Global`): the bot posts the English card and caption there, at the same time as the Persian channel. The bot must be an admin of that channel.
- `AUTO_PUBLISH` (default on): posts go straight to the channels and the admin gets a notification with a delete button. `AUTO_PUBLISH=0` restores approve/reject.

## Growth: "Up or Down?" game and invite rewards (`growth.py`)

- Daily at `GAME_HOUR_UTC` (default 15): a round in each public channel with ⬆️/⬇️ buttons; voting closes after `GAME_LOCK_HOURS` (default 2); settled 24 h later against the live BTC price, with a weekly leaderboard.
- Each Monday the best predictor of the week in each channel gets 30 days of Pro (a one-time invite link to the Pro channel).
- Anyone who opens the bot gets a personal invite link; every `REF_FRIENDS` (default 3) new members through it = `REF_PRO_DAYS` (default 7) days of Pro.
- The bot needs, in each public channel, the admin right to invite users via link (for personal links and join tracking).


## ریلز و تیک‌تاک از طریق بات تلگرام

بات برای ادمین و در بستهٔ روزانه `/kit`، علاوه بر عکس‌های مربعی و عمودی فارسی و انگلیسی، ویدیوهای کوتاه MP4 عمودی ۹:۱۶ تولید و به چت شخصی مدیر ارسال می‌کند. انتشار این ویدیوها در Instagram یا TikTok خودکار نیست؛ فایل را بررسی و خودتان منتشر کنید.

- `/reels`: فقط ساخت و ارسال ریلز ۱۵ ثانیه‌ای فارسی و انگلیسی از مهم‌ترین خبر ۲۴ ساعت اخیر
- `/kit`: تصاویر، کپشن، هشتگ‌ها و ریلزهای آماده
- `SOCIAL_REELS_ENABLED=0`: غیرفعال‌کردن تولید ویدیو (پیش‌فرض روشن)
- `SOCIAL_HOUR_UTC`: ساعت بستهٔ روزانه (پیش‌فرض ۱۶ به‌وقت UTC)
- `imageio-ffmpeg`: ابزار کدگذاری ویدیو که در `requirements.txt` نصب می‌شود

ویدیوها **بی‌صدا** هستند تا بتوانید صدای دلخواه یا موسیقی مجاز پلتفرم را اضافه کنید. کیفیت خروجی ۷۲۰×۱۲۸۰ و مدت ۱۵ ثانیه است. خرابی یا در دسترس نبودن پردازش ویدیو نباید فرایند ساخت خبر، پست تلگرام یا تصویر روزانه را متوقف کند.


### تحویل خودکار روزانه با تبلیغ سایت و کانال‌ها

- پیش‌فرض: یک **بسته** در روز، از ساعت **۱۹:۳۰ به وقت سوئد** (Europe/Stockholm، با تغییر خودکار ساعت تابستانی/زمستانی). نیاز به فرمان تلگرام نیست.
- هر بسته به چت خصوصی مدیر می‌رسد: تصویر مربعی و عمودی، کپشن و هشتگ، و ریلز ۱۵ثانیه‌ای فارسی و انگلیسی. برای انتشار دستی در Instagram/TikTok ساخته می‌شود و از این مسیر هیچ پستی خودکار در Instagram/TikTok منتشر نمی‌شود.
- تبلیغ سایت و لینک **هر دو کانال تلگرام** در کپشن‌ها، پایین تصاویر و صفحه پایانی ریلز قرار می‌گیرد.
- متغیرهای Render: `PUBLIC_SITE_URL` (آدرس واقعی سایت)، `PUBLIC_CHANNEL_URL` (لینک کانال فارسی)، `PUBLIC_CHANNEL_URL_EN` (لینک کانال انگلیسی). اگر کانال‌ها با `@username` در `TELEGRAM_CHANNEL_ID` و `TELEGRAM_CHANNEL_EN` آمده باشند، لینک `t.me` خودکار ساخته می‌شود؛ برای شناسه‌های عددی باید لینک عمومی را در متغیرهای بالا تنظیم کنید. **هرگز توکن بات را در GitHub ذخیره نکنید.**
- `SOCIAL_TIME_LOCAL=19:30` برای تغییر ساعت محلی؛ پیش‌فرض ۱۹:۳۰. `SOCIAL_REELS_ENABLED=0` برای غیرفعال‌کردن ریلز.
- یک GitHub Actions schedule در `.github/workflows/daily-social-wakeup.yml` هر ۱۵ دقیقه در بازهٔ عصرِ UTC سرویس Render رایگان را بیدار می‌کند. به صورت پیش‌فرض آدرس `https://cryptoai-main-site.onrender.com` را استفاده می‌کند. اگر URL واقعی سایت شما متفاوت است، repository variable با نام `SOCIAL_WAKE_URL` را روی URL درست سرویس Render تنظیم کنید (بدون `/api/health`). این workflow فقط سایت را بیدار می‌کند؛ ارسال واقعی بسته در سرور و با کنترل ساعت سوئد انجام می‌شود.
- تاریخ آخرین ارسال روزانه در نسخهٔ پشتیبان موجود در پیام سنجاق‌شدهٔ تلگرام ثبت می‌شود تا پس از راه‌اندازی مجدد، احتمال ارسال تکراری کمتر شود. اگر دادهٔ خبر تازه نباشد، بسته ارسال نمی‌شود و نوبت بعدی دوباره بررسی خواهد شد.

نکته: سرویس Render رایگان و GitHub Actions زمان‌بندی دقیق تا ثانیه را تضمین نمی‌کنند. اگر سرویس به دلیل خواب، خرابی یا محدودیت‌های ارائه‌دهنده در دسترس نباشد، ممکن است محتوا با تأخیر برسد.
