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
