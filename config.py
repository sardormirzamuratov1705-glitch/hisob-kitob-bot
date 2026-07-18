import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

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
