import os
from datetime import datetime, timedelta, timezone as _timezone
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

# ---------- 5-BOSQICH: VAQT MINTAQASI ----------
# Railway (va ko'pchilik boshqa hosting)da server odatda UTC vaqtida ishlaydi,
# lekin botning barcha foydalanuvchilari O'zbekistonda (UTC+5, DST YO'Q -
# yil bo'yi o'zgarmaydi). Agar bazaga/kunlik hisobot vaqtiga oddiy
# datetime.now() (ya'ni server/UTC vaqti) yozilsa - savdo vaqtlari, "bugungi
# holat", kunlik hisobot yuborilish vaqti va h.k. haqiqiy Toshkent vaqtidan
# 5 soatga siljib qoladi (masalan UTC kechasi soat 00:00-05:00 oralig'ida
# "bugun" Toshkentda allaqachon ERTASI kun bo'ladi).
#
# Shuning uchun butun botda datetime.now() o'RNIGA config.now() ishlatiladi -
# u har doim, server qayerda joylashganidan qat'i nazar, Toshkent vaqtini
# qaytaradi (naiv datetime sifatida, ya'ni .strftime()/.date()/timedelta
# arifmetikasi eskisidek ishlayveradi - hech qayerda qo'shimcha o'zgartirish
# kerak emas).
TASHKENT_TZ = _timezone(timedelta(hours=5))


def now() -> datetime:
    """Har doim Toshkent (UTC+5) vaqtini qaytaradi - server vaqti (odatda
    UTC) qanday bo'lishidan qat'i nazar. datetime.now()ning to'g'ridan-to'g'ri
    o'rnini bosadi (naiv datetime qaytaradi)."""
    return datetime.now(TASHKENT_TZ).replace(tzinfo=None)


# Mahsulot rasmlari shu kanalga yuboriladi va file_id o'sha yerdan olinadi.
# Kanal ID manfiy sondan boshlanadi, masalan: -1001234567890
# Botni shu kanalga ADMIN qilib qo'shish shart (aks holda rasm yubora olmaydi).
CHANNEL_ID = os.getenv("CHANNEL_ID", "")

# MUHIM: Railway'da Volume ulasangiz, uni /data ga mount qiling
# va DB_PATH ni /data/shop.db qilib environment variable orqali bering.
# Volume ulanmasa, bot ishlaydi, lekin redeploy'da baza tozalanadi.
DB_PATH = os.getenv("DB_PATH", "shop.db")

# WEBHOOK sozlamalari - polling o'rniga webhook ishlatish uchun.
# WEBHOOK_HOST ni Railway -> Settings -> Networking -> Public Domain'dan olib,
# "https://" bilan boshlab shu yerga variable qilib qo'ying, masalan:
# WEBHOOK_HOST=https://sizning-domeningiz.up.railway.app
# Agar WEBHOOK_HOST bo'sh bo'lsa, bot eski polling rejimida ishlayveradi.
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "").rstrip("/")
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}" if WEBHOOK_HOST else ""
PORT = int(os.getenv("PORT", "8080"))

# ---------- WEB APP (SAVDO) - 1-BOSQICH: INFRATUZILMA ----------
# Telegram "Mini App" (WebApp) - "🛒 Savdo" tugmasini bosganda Telegram
# ICHIDA ochiladigan veb-sahifa (aiohttp orqali shu botning o'zi xizmat
# qiladi). Bunga Telegramning o'zi ANIQ HTTPS manzil talab qiladi -
# shuning uchun WEBAPP_URL faqat WEBHOOK_HOST (yoki .env orqali alohida)
# sozlangandagina ishlaydi. Agar sozlanmagan bo'lsa (masalan hali polling
# rejimida, domensiz ishlab chiqilayotganda) - "🛒 Savdo" tugmasi ESKI
# (matn asosidagi, bosqichma-bosqich so'raydigan) usulda ishlayveradi -
# hech narsa buzilmaydi.
#
# .env orqali alohida domen berish mumkin (masalan WEBHOOK_HOST'dan farqli
# bo'lsa), aks holda avtomatik WEBHOOK_HOST asosida quriladi:
WEBAPP_URL = os.getenv("WEBAPP_URL", "").rstrip("/") or (
    f"{WEBHOOK_HOST}/webapp" if WEBHOOK_HOST else ""
)
# DIQQAT: bu yerga ?v=... kabi query-parametr QASDAN QO'SHILMAYDI - sinov
# shuni ko'rsatdiki, tugmaning o'zi ishora qiladigan manzilda query bo'lsa,
# Telegram (ba'zi versiyalarda) tgWebAppData'ni butunlay yubormay qo'yadi
# (foydalanuvchi "Ruxsat yo'q" xatosini olgan). Kesh muammosi endi FAQAT
# ichki app.js/style.css havolalariga versiya qo'shish orqali hal qilinadi
# (webapp.py'dagi _STARTUP_VERSION) - bu tugma manzilining o'zini
# o'zgartirmaydi.
# Statik fayllar (index.html, app.js, style.css) shu papkada saqlanadi.
WEBAPP_STATIC_DIR = os.getenv("WEBAPP_STATIC_DIR", "webapp_static")

# ---------- OBUNA TARIFLARI VA TO'LOV REKVIZITLARI (6-BOSQICH) ----------
# DIQQAT: quyidagi narxlar va rekvizitlar VAQTINCHALIK QIYMATLAR - haqiqiy
# ishga tushirishdan oldin .env orqali (yoki shu yerda to'g'ridan-to'g'ri)
# o'zingizning narxlaringiz/karta-Click-Payme raqamlaringizga almashtiring!
SUBSCRIPTION_PRICE_1_MONTH = int(os.getenv("SUBSCRIPTION_PRICE_1_MONTH", "50000"))
SUBSCRIPTION_PRICE_3_MONTHS = int(os.getenv("SUBSCRIPTION_PRICE_3_MONTHS", "135000"))
SUBSCRIPTION_PRICE_12_MONTHS = int(os.getenv("SUBSCRIPTION_PRICE_12_MONTHS", "480000"))

PAYMENT_CARD_NUMBER = os.getenv("PAYMENT_CARD_NUMBER", "8600 1234 5678 9012")
PAYMENT_CARD_HOLDER = os.getenv("PAYMENT_CARD_HOLDER", "F.I.Sh. To'ldiring")
PAYMENT_CLICK_NUMBER = os.getenv("PAYMENT_CLICK_NUMBER", "+998 90 123 45 67")
PAYMENT_PAYME_NUMBER = os.getenv("PAYMENT_PAYME_NUMBER", "+998 90 123 45 67")

# ---------- 6-BOSQICH: KUNLIK HISOBOT YUBORISH VAQTI ----------
# Har kuni shu vaqtda (O'ZBEKISTON/Toshkent vaqti bo'yicha, UTC+5 - config.now()
# orqali, server qayerda joylashganidan qat'i nazar) barcha
# do'kon egalariga avtomatik kunlik hisobot yuboriladi (alerts.py,
# main.py._daily_report_loop). .env orqali "HH:MM" formatida o'zgartiring,
# masalan: DAILY_REPORT_TIME=21:30
# Noto'g'ri format kiritilsa (masalan xato yozilsa) - xavfsiz standart
# qiymat (21:00) ishlatiladi, bot ishga tushmay qolmaydi.
_daily_report_time_raw = os.getenv("DAILY_REPORT_TIME", "21:00")
try:
    _hour_str, _minute_str = _daily_report_time_raw.strip().split(":")
    DAILY_REPORT_HOUR = int(_hour_str)
    DAILY_REPORT_MINUTE = int(_minute_str)
    if not (0 <= DAILY_REPORT_HOUR <= 23 and 0 <= DAILY_REPORT_MINUTE <= 59):
        raise ValueError
except (ValueError, AttributeError):
    DAILY_REPORT_HOUR, DAILY_REPORT_MINUTE = 21, 0

# ---------- SHUBHALI HOLATLAR - 8-BOSQICH: STANDART CHEGARALAR ----------
# Bu yerdagi qiymatlar - FAQAT standart (default). Har bir do'kon egasi
# "🔔 Kunlik hisobot" kabi o'z sozlamalar bo'limidan bularni O'ZIGA moslab
# o'zgartira oladi (database.get_suspicious_rules/set_suspicious_rule,
# settings jadvalida shop_id bo'yicha alohida saqlanadi) - shu sabab bu
# yerdagi qiymatlar faqat hali hech narsa sozlanmagan yangi do'konlar uchun
# "boshlang'ich" son sifatida ishlatiladi.
#
# 1) Manfiy qoldiq va 2) tannarxdan past sotish - chegarasiz, doim yoqilgan
#    tekshiruvlar (bular sozlanmaydi, shuning uchun bu yerda yo'q).
#
# 3) G'ayrioddiy katta chegirma - sotuv narxi tavsiya etilgan sell_price'dan
#    necha FOIZ past bo'lsa shubhali hisoblanadi.
SUSPICIOUS_DISCOUNT_PERCENT = int(os.getenv("SUSPICIOUS_DISCOUNT_PERCENT", "20"))

# 4) Bitta savdoda (bitta chekda, bitta mahsulotdan) necha DONADAN ko'p
#    sotilsa shubhali hisoblanadi.
SUSPICIOUS_SALE_QUANTITY = float(os.getenv("SUSPICIOUS_SALE_QUANTITY", "50"))

# 5) Bitta chiqim (kirim-chiqimdagi "chiqim" yozuvi) necha SO'MDAN yuqori
#    bo'lsa shubhali hisoblanadi - qo'lda oldindan kiritilgan standart qiymat,
#    do'kon egasi o'zi sozlashi mumkin.
SUSPICIOUS_EXPENSE_AMOUNT = float(os.getenv("SUSPICIOUS_EXPENSE_AMOUNT", "500000"))

# 6) Ish vaqti oralig'i - shu oraliqdan TASHQARIDA kiritilgan savdo/chiqim
#    shubhali hisoblanadi. Standart qiymat qo'lda kiritilgan (08:00-22:00),
#    do'kon egasi o'zining ish vaqtiga moslab o'zgartira oladi.
SUSPICIOUS_WORK_HOUR_START = int(os.getenv("SUSPICIOUS_WORK_HOUR_START", "8"))
SUSPICIOUS_WORK_HOUR_END = int(os.getenv("SUSPICIOUS_WORK_HOUR_END", "22"))

# 7) Bir kunda bitta xodimdan (performed_by) necha TADAN ko'p savdo/chiqim
#    yozuvi kiritilsa shubhali hisoblanadi.
SUSPICIOUS_SELLER_DAILY_COUNT = int(os.getenv("SUSPICIOUS_SELLER_DAILY_COUNT", "15"))

# ---------- QARZ ESLATMASI - 13-BOSQICH: MUDDATI O'TGANLAR ----------
# due_date belgilanmagan qarzlar uchun - yaratilganidan necha kun o'tsa
# "muddati o'tgan" hisoblanadi (alerts.send_debt_reminders standart qiymati).
DEBT_OVERDUE_DAYS_DEFAULT = int(os.getenv("DEBT_OVERDUE_DAYS_DEFAULT", "3"))

# Mijozga to'g'ridan-to'g'ri (start-link orqali bog'langan bo'lsa) eslatma
# necha KUNDA BIR MARTA yuboriladi - mijozni HAR KUNI bezovta qilmaslik
# uchun. Do'kon egasiga esa bundan qat'i nazar har kuni to'liq ro'yxat
# ketaveradi (o'zi bilishi kerak, mijoz esa kamroq bezovta bo'lsin).
DEBT_CUSTOMER_REMINDER_INTERVAL_DAYS = int(os.getenv("DEBT_CUSTOMER_REMINDER_INTERVAL_DAYS", "3"))

# ---------- AI BUYURTMA TAVSIYASI - 16-BOSQICH ----------
# Mahsulot yetkazib berish odatda necha KUN vaqt oladi (standart qiymat -
# har bir do'kon egasi "🤖 AI buyurtma tavsiyasi" bo'limidan o'ziga moslab
# o'zgartira oladi, database.get_restock_lead_time_days/set_restock_lead_time_days).
# Joriy qoldiq shu necha kunlik sotishga YETMAYDIGAN bo'lsa - "hozir
# buyurtma bering" deb tavsiya beriladi (aks holda tovar yetib kelguncha
# sklad tugab qolishi mumkin).
RESTOCK_LEAD_TIME_DAYS_DEFAULT = int(os.getenv("RESTOCK_LEAD_TIME_DAYS_DEFAULT", "7"))

# Tariflar ro'yxati - handlers/subscription.py shu yerdan o'qiydi (tugmalar,
# narx ko'rsatish va tanlangan tarifga qarab subscription_until'ni necha
# kunga uzaytirish kerakligini aniqlash uchun). "days" - 7-bosqichda
# to'lov tasdiqlanganda owners.subscription_until shunga qarab uzaytiriladi.
SUBSCRIPTION_PLANS = {
    "1m": {
        "label": "1 oy",
        "days": 30,
        "price": SUBSCRIPTION_PRICE_1_MONTH,
        "discount_note": None,
    },
    "3m": {
        "label": "3 oy",
        "days": 90,
        "price": SUBSCRIPTION_PRICE_3_MONTHS,
        "discount_note": "chegirmali",
    },
    "12m": {
        "label": "12 oy",
        "days": 365,
        "price": SUBSCRIPTION_PRICE_12_MONTHS,
        "discount_note": "chegirmali",
    },
}
