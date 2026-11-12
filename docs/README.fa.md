# راهنمای فارسی Xray Gemini Browser Audit

**نسخه مستند: 1.0.0**

این پروژه برای ارزیابی عملکرد **Gemini Web** از مسیر کانفیگ‌های VLESS/Xray است. برنامه از Google Chrome معمولی، Playwright/CDP و Xray رسمی داخل Docker استفاده می‌کند. موفقیت Web به معنی موفقیت قطعی **Gemini Android** یا تأیید IP خروجی نیست.

برای توضیح فنی کامل، محدودیت‌ها و همه پارامترها به [README اصلی](../README.md) مراجعه کن.

## پیش‌نیازها

- لپ‌تاپ لینوکسی با محیط گرافیکی، Python 3.10 یا جدیدتر
- Google Chrome نصب‌شده
- Docker فعال و قابل اجرا با کاربر فعلی
- کانفیگ VLESS TCP/RAW یا لینک Subscription با فهرست VLESS

## نصب

```bash
git clone https://github.com/h-zare-dev/xray-gemini-browser-audit.git
cd xray-gemini-browser-audit
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
docker pull ghcr.io/xtls/xray-core:26.3.27
```

## ساخت فایل تنظیمات محرمانه

```bash
cp -n .env.example .env
chmod 600 .env
nano .env
```

**فایل موجود `.env` را بازنویسی نکن.** این فایل و پوشه نشست Google با `.gitignore` از GitHub کنار گذاشته می‌شوند.

### حالت اول: یک کانفیگ، چند پورت

```dotenv
MODE=vless
VLESS_URL=vless://YOUR-PRIVATE-CONNECTION
PORTS=23001,23004,23007,24001-24009
SUBSCRIPTION_URL=
```

در این حالت آدرس و مشخصات کانفیگ ثابت است و فقط پورت مقصد بر اساس فهرست تست می‌شود. بازه `24001-24009` شامل ابتدا و انتها است.

### حالت دوم: لینک Subscription

```dotenv
MODE=subscription
SUBSCRIPTION_URL=https://your-provider.example/private-subscription
```

هر کانفیگ VLESS سازگار، با آدرس و پورت خودش بررسی می‌شود. در این حالت `PORTS` استفاده نمی‌شود. فعلاً Subscription متنی یا Base64 حاوی لینک‌های VLESS با شبکه TCP/RAW پشتیبانی می‌شود؛ Clash YAML/JSON، VMess، Trojan و Transportهایی مانند WS، gRPC و XHTTP در این نسخه پشتیبانی نمی‌شوند.

## اجرای برنامه

```bash
# همه موارد تعریف‌شده در .env
python src/session_audit.py

# سه پورت نمونه در حالت vless
python src/session_audit.py --ports 23001,23004,23007

# راهنمای گزینه‌های ترمینال
python src/session_audit.py --help
```

با `LOGIN_DIRECT=true`، ابتدا Chrome بدون پروکسی Xray برای ورود دستی باز می‌شود. بعد از ورود، در ترمینال Enter بزن. برنامه پنجره ورود را می‌بندد، مرورگر دیگری با همان پروفایل و از طریق Xray باز می‌کند و تست‌ها را شروع می‌کند. با `CLOSE_BROWSER=true` مرورگر اختصاصی تست در پایان بسته می‌شود.

اگر Google هنگام تغییر IP دوباره ورود یا تأیید هویت خواست، این موضوع به‌تنهایی نشان‌دهنده خرابی کانفیگ نیست.

## تنظیمات پیشنهادی

```dotenv
RETRIES=3
READY_WAIT=15
ANSWER_WAIT=70
TIMEOUT=55
RESPONSE_STABLE=4
RETRY_DELAY=7
PAUSE=8

LOGIN_DIRECT=true
CLOSE_BROWSER=true
CHROME_PATH=
PROFILE_DIR=.local/browser-profile

SOCKS_PORT=18998
XRAY_IMAGE=ghcr.io/xtls/xray-core:26.3.27
XRAY_STARTUP_TIMEOUT=20

OUTPUT_DIR=reports/session
```

- `READY_WAIT`: زمان **قبل از ارسال پیام** برای بازشدن صفحه و پیدا شدن کادر ورودی.
- `ANSWER_WAIT`: فقط **بعد از ارسال پیام** آغاز می‌شود؛ برای Gemini Pro می‌توان آن را افزایش داد.
- `RETRIES`: حداکثر تلاش برای نتیجه‌های خطادار یا نامشخص. پاسخ موفق یا صفحه صریح محدودیت کشور، همان تلاش اول خاتمه پیدا می‌کند.
- `RESPONSE_STABLE`: مدت ثابت‌ماندن پاسخ Gemini قبل از تأیید موفقیت.
- `PAUSE` و `RETRY_DELAY`: فاصله بین پورت‌ها و بین تلاش‌های مجدد.
- `OUTPUT_DIR`: پوشه اصلی نتایج.

تمام این موارد از `.env` خوانده می‌شوند؛ آرگومان ترمینال در صورت وجود اولویت دارد.

## نتیجه هر اجرا

برای هر اجرا یک پوشه یکتا با تاریخ و ساعت محلی ساخته می‌شود:

```text
reports/session/
  2026-11-12_21-30-45/
    results.csv
    0001_23001_try1.png
    0002_23004_try1.png
  2026-11-12_22-10-03/
    results.csv
```

`OK / WEB_OK` یعنی پاسخ مورد انتظار داخل بخش پاسخ مدل پیدا شده است؛ `BLOCKED / REGION_BLOCKED` یعنی صفحه صریحاً اعلام کرده Gemini در آن کشور پشتیبانی نمی‌شود؛ `CHECK` یعنی نتیجه هنوز قطعی نیست، مثلاً کادر پیام نمایش داده نشده یا نشست Google نامعتبر شده است. **هیچ سروری را صرفاً بر اساس CHECK از Balancer حذف نکن.**

## بررسی و عیب‌یابی

```bash
python -m compileall -q src
python -m unittest discover -s tests -p 'test_*.py'
```

- **Google اجازه Login نمی‌دهد:** از حالت ورود مستقیم بدون Xray استفاده کن؛ Google ممکن است بعضی نشست‌ها را محدود کند.
- **صفحه کشور پشتیبانی نمی‌شود:** در خروجی باید `BLOCKED` ثبت شود و همان پورت دوباره تست نشود.
- **کادر پیام پیدا نشد:** `NO_EDITOR` نتیجه نامشخص است؛ اسکرین‌شات را بررسی کن.
- **خطای تغییر شبکه:** هنگام جابه‌جایی اتصال Xray امکان `ERR_NETWORK_CHANGED` وجود دارد؛ Retry و فاصله تست‌ها را تنظیم کن.
- **Gemini پاسخ می‌دهد اما CHECK می‌گیری:** ممکن است ساختار HTML تغییر کرده باشد یا پاسخ با زمان تنظیم‌شده تثبیت نشده باشد.
- **Chrome در حال استفاده از پروفایل است:** پنجره‌های قبلی مربوط به `PROFILE_DIR` را ببند.

## امنیت و محدودیت‌ها

لینک VLESS، UUID، توکن Subscription، رمز Google و فایل‌های پروفایل را داخل GitHub قرار نده. اسکرین‌شات‌ها و CSV نیز محلی می‌مانند. این برنامه مستقل از پنل production است و تغییری در Balancer یا Xray اصلی نمی‌دهد. به‌دلیل احتمال استفاده مجدد Chrome از اتصال‌های قبلی، برنامه **IP خروجی واقعی هر پورت را مستقلاً تأیید نمی‌کند**؛ برای تصمیم عملیاتی به آزمون تکمیلی نیاز داری.

نسخه فعلی در فایل [VERSION](../VERSION) ثبت شده و تغییرات در [CHANGELOG](../CHANGELOG.md) آمده است. ثبت شماره نسخه در مخزن به‌خودی‌خود به معنی ساخت Git tag یا GitHub Release نیست.
