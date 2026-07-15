import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

# MUHIM: Railway'da Volume ulasangiz, uni /data ga mount qiling
# va DB_PATH ni /data/shop.db qilib environment variable orqali bering.
# Volume ulanmasa, bot ishlaydi, lekin redeploy'da baza tozalanadi.
DB_PATH = os.getenv("DB_PATH", "shop.db")
