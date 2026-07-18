import os
import secrets
from datetime import datetime, timedelta

import aiosqlite

import config


# ---------- OBUNA TIZIMI SOZLAMALARI ----------
# Yangi ro'yxatdan o'tgan do'kon egasiga beriladigan bepul sinov muddati.
SUBSCRIPTION_TRIAL_DAYS = 14
# Obuna tizimi kodga qo'shilishidan OLDIN allaqachon mavjud bo'lgan (eski)
# do'kon egalari to'satdan bloklanib qolmasligi uchun bir martalik
# "sovg'a" muddati - init_db() ichida faqat subscription_status hali
# NULL bo'lgan qatorlarga qo'llaniladi (1-bosqich, moslik siyosati).
# Obuna tugaganidan keyin ham botga kirish davom etadigan "muhlat" - odam
# birdan bloklanib qolmasligi, to'lov qilishga vaqt topishi uchun.
SUBSCRIPTION_GRACE_DAYS = 3


def compute_subscription_access(subscription_status: str, subscription_until: str) -> dict:
    """Berilgan subscription_status/subscription_until asosida "hozir botga
    kirish mumkinmi" degan YAGONA hisoblashni bajaradi. Bu funksiya faqat
    hisoblaydi - hech kimni bloklamaydi (bloklash middleware'i 5-bosqichda
    shu funksiya natijasidan foydalanadi).

    Qaytaradi:
        {
            "allowed": bool,     - hozircha kirish mumkinmi
            "status": str,       - "trial" | "active" | "expired" | "blocked" | "unknown"
            "days_left": int | None,  - subscription_until'gacha necha kun qoldi
                                         (manfiy - necha kun oldin tugagan)
            "in_grace": bool,    - muddat tugagan, lekin SUBSCRIPTION_GRACE_DAYS
                                   ichida (hali "expired" lekin vaqtincha ochiq)
        }
    """
    if subscription_status == "blocked":
        # Bosh admin majburan yopgan - grace period ham qo'llanmaydi.
        return {"allowed": False, "status": "blocked", "days_left": None, "in_grace": False}

    if not subscription_status or not subscription_until:
        # Obuna tizimi hali bu ega uchun ishlamagan/noma'lum holat (nazariy
        # jihatdan bo'lmasligi kerak, chunki init_db() barcha eskilarga ham
        # qiymat beradi) - xavfsiz tomonga og'ib ruxsat beramiz.
        return {"allowed": True, "status": "unknown", "days_left": None, "in_grace": False}

    try:
        until_date = datetime.strptime(subscription_until, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return {"allowed": True, "status": "unknown", "days_left": None, "in_grace": False}

    days_left = (until_date - datetime.now().date()).days

    if days_left >= 0:
        # "trial" yoki "active" - muddat hali tugamagan.
        return {"allowed": True, "status": subscription_status, "days_left": days_left, "in_grace": False}

    days_overdue = -days_left
    if days_overdue <= SUBSCRIPTION_GRACE_DAYS:
        return {"allowed": True, "status": "expired", "days_left": days_left, "in_grace": True}

    return {"allowed": False, "status": "expired", "days_left": days_left, "in_grace": False}


async def get_owner_subscription_access(owner_telegram_id: int) -> dict | None:
    """compute_subscription_access() ni bazadan shu ega uchun subscription_status/
    subscription_until'ni o'qib chaqiradi. Ega topilmasa - None."""
    owner = await get_owner(owner_telegram_id)
    if not owner:
        return None
    return compute_subscription_access(owner.get("subscription_status"), owner.get("subscription_until"))


async def init_db():
    db_dir = os.path.dirname(config.DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shop_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                quantity REAL NOT NULL,
                photo_file_id TEXT,
                channel_message_id INTEGER,
                sell_price REAL,
                min_price REAL,
                alert_quantity REAL,
                created_at TEXT NOT NULL
            )
            """
        )
        # Eski bazalarda bu ustunlar bo'lmasligi mumkin - xavfsiz qo'shib qo'yamiz.
        for column, col_type in [
            ("channel_message_id", "INTEGER"),
            ("sell_price", "REAL"),
            ("min_price", "REAL"),
            ("alert_quantity", "REAL"),
            ("last_sold_at", "TEXT"),
            ("shop_id", "INTEGER"),
            ("category_id", "INTEGER"),
        ]:
            try:
                await db.execute(f"ALTER TABLE products ADD COLUMN {column} {col_type}")
            except Exception:
                pass
        # Mahsulot bo'limlari - har bir do'kon egasi o'zi xohlagancha
        # bo'lim yarata oladi (masalan "Ichimliklar", "Non mahsulotlari").
        # Bo'limga bog'lanish ixtiyoriy - mahsulot bo'limsiz ham qolishi mumkin.
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shop_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shop_id INTEGER NOT NULL,
                type TEXT NOT NULL,
                amount REAL NOT NULL,
                description TEXT,
                created_at TEXT NOT NULL,
                payment_method TEXT
            )
            """
        )
        for column, col_type in [
            ("payment_method", "TEXT"),
            ("shop_id", "INTEGER"),
            ("branch_id", "INTEGER"),
        ]:
            try:
                await db.execute(f"ALTER TABLE transactions ADD COLUMN {column} {col_type}")
            except Exception:
                pass
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS restock_manual (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shop_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                note TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        try:
            await db.execute("ALTER TABLE restock_manual ADD COLUMN shop_id INTEGER")
        except Exception:
            pass
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS debts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shop_id INTEGER NOT NULL,
                customer_name TEXT NOT NULL,
                phone TEXT,
                amount REAL NOT NULL,
                description TEXT,
                is_paid INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                due_date TEXT,
                customer_chat_id INTEGER,
                customer_username TEXT,
                taken_date TEXT,
                paid_amount REAL NOT NULL DEFAULT 0
            )
            """
        )
        # Har bir qisman/to'liq to'lovni alohida qayd etib boramiz (tarix uchun).
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS debt_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                debt_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                paid_at TEXT NOT NULL
            )
            """
        )
        # Eski bazalarda bu ustunlar bo'lmasligi mumkin - xavfsiz qo'shib qo'yamiz.
        for column, col_type in [
            ("due_date", "TEXT"),
            ("customer_chat_id", "INTEGER"),
            ("customer_username", "TEXT"),
            ("taken_date", "TEXT"),
            ("paid_amount", "REAL NOT NULL DEFAULT 0"),
            ("shop_id", "INTEGER"),
            ("branch_id", "INTEGER"),
        ]:
            try:
                await db.execute(f"ALTER TABLE debts ADD COLUMN {column} {col_type}")
            except Exception:
                pass
        # Har bir savdo cheki ichidagi mahsulotlar - qaysi tovarlar birga
        # sotilganini bilish uchun (bog'lab sotish taklifi/cross-sell).
        # sale_id - transactions.id (bitta savdo cheki bitta transaction).
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS sale_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shop_id INTEGER NOT NULL,
                sale_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                quantity REAL NOT NULL,
                price REAL NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        try:
            await db.execute("ALTER TABLE sale_items ADD COLUMN shop_id INTEGER")
        except Exception:
            pass
        # Do'kon egalari (bosh admin tomonidan bot orqali qo'shiladigan foydalanuvchilar).
        # Bosh admin - config.ADMIN_IDS (.env), faqat shu ro'yxatdagilar bu jadvalga
        # yozuv qo'sha/o'chira oladi. Har bir do'kon egasi - alohida, mustaqil do'kon
        # (shop_id = shu egasining telegram_id'si); boshqa do'kon egasining
        # ma'lumotlarini ko'rmaydi/o'zgartira olmaydi.
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS owners (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL UNIQUE,
                full_name TEXT,
                username TEXT,
                added_by INTEGER,
                created_at TEXT NOT NULL
            )
            """
        )
        # Bosh admin tomonidan yaratiladigan bir martalik taklif linklari -
        # har bir link faqat BITTA odam tomonidan ishlatilishi mumkin
        # (link.used_by bo'sh bo'lsa - hali ishlatilmagan, ishlatilgach
        # boshqa hech kim shu link orqali qo'shila olmaydi).
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS owner_invites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT NOT NULL UNIQUE,
                created_by INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                used_by INTEGER,
                used_at TEXT
            )
            """
        )
        # Sotuvchilar - do'kon egasi tomonidan o'z do'koniga qo'shiladigan xodimlar.
        # Har bir sotuvchi FAQAT bitta do'konga (shop_id) tegishli - do'kon egasi
        # boshqa do'konning sotuvchisini ko'rmaydi/boshqara olmaydi. Sotuvchining
        # o'z do'koni yo'q, ruxsatlari cheklangan (narx belgilash, qo'lda miqdor
        # o'zgartirish, kirim/chiqim, hisobot - unga yopiq, access_control.py'ga qarang).
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS sellers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL UNIQUE,
                shop_id INTEGER NOT NULL,
                full_name TEXT,
                username TEXT,
                added_by INTEGER,
                created_at TEXT NOT NULL
            )
            """
        )
        # Sotuvchi uchun bir martalik taklif linklari - owner_invites'ga o'xshaydi,
        # lekin shop_id bilan bog'langan (faqat shu do'konga sotuvchi qo'shadi).
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS seller_invites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT NOT NULL UNIQUE,
                shop_id INTEGER NOT NULL,
                created_by INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                used_by INTEGER,
                used_at TEXT
            )
            """
        )
        # Har bir yozuvni KIM bajarganini bilish uchun (do'kon egasimi, qaysi
        # sotuvchimi) - bir nechta sotuvchi bo'lsa, egasi keyin kim qancha savdo
        # qilgani/kamomad bormi tekshira oladi. Eski bazalarda yo'q - xavfsiz qo'shamiz.
        for table in ("transactions", "sale_items", "debts", "debt_payments"):
            try:
                await db.execute(f"ALTER TABLE {table} ADD COLUMN performed_by INTEGER")
            except Exception:
                pass

        # Qarz to'lovini ham naqd/plastik/aralash qilib to'lash imkoni uchun -
        # savdo va kirim-chiqimdagi kabi to'lov turini shu yerda ham saqlaymiz.
        try:
            await db.execute("ALTER TABLE debt_payments ADD COLUMN payment_method TEXT")
        except Exception:
            pass

        # Do'kon egasining o'zi kiritgan ismi va do'kon nomi/turi - bosh admin
        # bir nechta do'kon egasini boshqarganda ularni Telegram ID/username
        # emas, balki tanish nom bilan bir-biridan ajratib olishi uchun.
        # Eski bazalarda yo'q - xavfsiz qo'shamiz (ALTER TABLE ADD COLUMN
        # allaqachon mavjud bo'lsa xato beradi, shuning uchun try/except).
        for col in ("owner_name", "shop_name", "phone_number"):
            try:
                await db.execute(f"ALTER TABLE owners ADD COLUMN {col} TEXT")
            except Exception:
                pass
        # Do'kon egasi hozir qaysi filialda "turibdi" - savdo/kirim-chiqim/qarz
        # yozuvlari shu filialga yoziladi. NULL = hali filial tanlanmagan
        # (yoki umuman filial qo'shilmagan) - "Bosh filial" sifatida ishlaydi.
        try:
            await db.execute("ALTER TABLE owners ADD COLUMN current_branch_id INTEGER")
        except Exception:
            pass

        # Sotuvchining o'zi kiritgan ismi va telefon raqami - do'kon egasi
        # bir nechta sotuvchini boshqarganda ularni Telegram ID/username
        # emas, balki tanish nom bilan bir-biridan ajratib olishi uchun.
        for col in ("seller_name", "phone_number"):
            try:
                await db.execute(f"ALTER TABLE sellers ADD COLUMN {col} TEXT")
            except Exception:
                pass
        # Sotuvchi doimiy ravishda bitta filialga qarab turadi - do'kon egasi
        # sotuvchi qo'shgan paytda o'zining joriy filiali avtomatik yoziladi,
        # keyinchalik egasi buni qo'lda boshqa filialga ko'chirishi mumkin.
        # Sotuvchining o'zi filial almashtira olmaydi. NULL = "Bosh filial".
        try:
            await db.execute("ALTER TABLE sellers ADD COLUMN branch_id INTEGER")
        except Exception:
            pass
        # Taklif linki yaratilgan paytda egasining joriy filiali shu yerga
        # yoziladi - link ishlatilib sotuvchi qo'shilganda shu qiymat
        # sellers.branch_id'ga ko'chadi (handlers/start.py).
        try:
            await db.execute("ALTER TABLE seller_invites ADD COLUMN branch_id INTEGER")
        except Exception:
            pass
        # Filiallar - har bir do'kon egasi o'zining bir nechta jismoniy
        # filialini (do'kon nuqtasini) qo'sha oladi. Hozircha faqat
        # tashkiliy/ma'lumot uchun - mahsulot/savdo filialga majburiy
        # bog'lanmaydi, egasi keyinchalik xohlagancha ishlata oladi.
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS branches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shop_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                address TEXT,
                created_at TEXT NOT NULL
            )
            """
        )

        # ---------- OBUNA TIZIMI ----------
        # Har bir do'kon egasi obuna holatiga ega:
        #   "trial"   - bepul sinov muddatida
        #   "active"  - to'langan/faol
        #   "expired" - muddati tugagan (hali bloklash/eslatma logikasi
        #               keyingi bosqichlarda qo'shiladi, bu yerda faqat ustun)
        #   "blocked" - bosh admin tomonidan majburan yopilgan
        # subscription_until - obuna qaysi sanagacha amal qilishi (YYYY-MM-DD).
        # trial_used - shu ega birinchi (bepul) sinov muddatidan foydalanganmi -
        # keyinchalik qayta ro'yxatdan o'tib yana trial olishning oldini olish uchun.
        for column, col_type in [
            ("subscription_status", "TEXT"),
            ("subscription_until", "TEXT"),
            ("trial_used", "INTEGER NOT NULL DEFAULT 0"),
        ]:
            try:
                await db.execute(f"ALTER TABLE owners ADD COLUMN {column} {col_type}")
            except Exception:
                pass

        # MOSLIK: bu funksiya qo'shilishidan OLDIN allaqachon ro'yxatdan o'tgan
        # do'kon egalarida subscription_status hali NULL (yuqoridagi ALTER TABLE
        # ularga qiymat bermaydi). Ularni to'satdan bloklab qo'ymaslik uchun bir
        # martalik SUBSCRIPTION_GRANDFATHER_DAYS kunlik faol obuna beramiz.
        # Shart faqat subscription_status IS NULL qatorlarga tegadi - shuning
        # uchun bu UPDATE har init_db() chaqirilganda ishlasa ham, allaqachon
        # qiymat olgan qatorlarni qayta o'zgartirmaydi (idempotent).
        grandfather_until = (datetime.now() + timedelta(days=SUBSCRIPTION_GRANDFATHER_DAYS)).strftime("%Y-%m-%d")
        await db.execute(
            "UPDATE owners SET subscription_status = 'active', subscription_until = ?, "
            "trial_used = 1 WHERE subscription_status IS NULL",
            (grandfather_until,),
        )

        # Har bir to'lov urinishi (hozircha qo'lda tasdiqlanadigan chek,
        # keyinchalik Click/Payme orqali avtomatik tasdiqlanadigan to'lovlar ham
        # shu jadvalga yoziladi) - bosh admin "kutilayotgan to'lovlar"ni shu
        # yerdan ko'radi; tasdiqlangach owners.subscription_until shunga qarab
        # uzaytiriladi (keyingi bosqichlarda).
        #   plan   - tarif nomi ("1oy" / "3oy" / "12oy" / "erkin")
        #   days   - shu to'lov qancha kunlik obuna berishi (erkin muddatda
        #            admin qo'lda kiritadigan qiymat shu yerga yoziladi)
        #   status - "pending" / "approved" / "rejected"
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                plan TEXT,
                days INTEGER,
                method TEXT NOT NULL DEFAULT 'qolda',
                status TEXT NOT NULL DEFAULT 'pending',
                screenshot_file_id TEXT,
                comment TEXT,
                created_at TEXT NOT NULL,
                decided_by INTEGER,
                decided_at TEXT
            )
            """
        )

        await db.commit()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _branch_filter(branch_id, column: str = "branch_id"):
    """Hisobotlarni filial bo'yicha filtrlash uchun umumiy yordamchi.

    branch_id=None  -> filtr yo'q (barcha filiallar - "Umumiy hisobot").
    branch_id=0     -> faqat branch_id IS NULL bo'lgan yozuvlar ("Bosh filial" -
                        filial tizimi qo'shilishidan oldingi eski yozuvlar ham shu yerga tushadi).
    branch_id=<int> -> faqat shu filialga tegishli yozuvlar.
    """
    if branch_id is None:
        return "", []
    if branch_id == 0:
        return f" AND {column} IS NULL", []
    return f" AND {column} = ?", [branch_id]


async def _ensure_category_schema(db):
    """Himoya chorasi: agar biror sababdan init_db() yangi bo'lim sxemasini
    hali yaratmagan bo'lsa (masalan eski jarayon hali qayta ishga tushmagan bo'lsa),
    har bir bo'lim bilan ishlaydigan funksiya chaqirilganda sxema shu yerda
    ham xavfsiz tarzda yaratib/qo'shib qo'yiladi."""
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    try:
        await db.execute("ALTER TABLE products ADD COLUMN category_id INTEGER")
    except Exception:
        pass
    await db.commit()


# ---------- MAHSULOTLAR (SKLAD) ----------

async def add_product(shop_id: int, name: str, price: float, quantity: float, photo_file_id,
                       channel_message_id=None, sell_price=None, min_price=None,
                       alert_quantity=None, category_id=None):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await _ensure_category_schema(db)
        await db.execute(
            "INSERT INTO products (shop_id, name, price, quantity, photo_file_id, channel_message_id, "
            "sell_price, min_price, alert_quantity, category_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (shop_id, name, price, quantity, photo_file_id, channel_message_id, sell_price, min_price,
             alert_quantity, category_id, _now()),
        )
        await db.commit()


async def get_product(shop_id: int, product_id: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM products WHERE id = ? AND shop_id = ?", (product_id, shop_id)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def update_product_quantity(shop_id: int, product_id: int, quantity: float):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "UPDATE products SET quantity = ? WHERE id = ? AND shop_id = ?",
            (quantity, product_id, shop_id),
        )
        await db.commit()


async def update_product_purchase(shop_id: int, product_id: int, add_quantity: float,
                                    purchase_price: float, sell_price: float, min_price: float,
                                    alert_quantity=None):
    """Kam qolgan mahsulot qayta sotib olinganda: miqdorni qo'shadi.

    Tannarx (price) o'rtacha tannarx (weighted average) usulida hisoblanadi -
    eskisi butunlay yangisiga almashtirilmaydi, aks holda foyda hisobi buziladi.
    Masalan: skladda 5 dona 20 000 so'mdan bor edi, endi 10 dona 50 000 so'mdan
    qo'shilsa - yangi tannarx (5*20000 + 10*50000) / 15 = 40 000 so'm bo'ladi.
    Savdo narxi va eng past narx esa xodim kiritgan yangi qiymatga to'g'ridan-to'g'ri o'zgaradi.
    """
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT quantity, price FROM products WHERE id = ? AND shop_id = ?",
            (product_id, shop_id),
        )
        row = await cursor.fetchone()
        if not row:
            return None

        old_quantity = row["quantity"]
        old_price = row["price"] or 0
        new_quantity = old_quantity + add_quantity

        if new_quantity > 0:
            weighted_price = (
                (old_quantity * old_price) + (add_quantity * purchase_price)
            ) / new_quantity
        else:
            weighted_price = purchase_price

        await db.execute(
            "UPDATE products SET quantity = ?, price = ?, sell_price = ?, min_price = ?, "
            "alert_quantity = ? WHERE id = ? AND shop_id = ?",
            (new_quantity, weighted_price, sell_price, min_price, alert_quantity, product_id, shop_id),
        )
        await db.commit()
        return new_quantity, weighted_price


async def find_product_by_name(shop_id: int, name: str):
    """Mahsulotni nomi bo'yicha qidiradi - katta-kichik harf va boshi/oxiridagi
    bo'sh joylarga qaramaydi (masalan "Un", "un", " UN " - bittasi deb topiladi).
    Shu orqali bitta mahsulot skladga ikki marta alohida qator sifatida
    kiritilib qolishining oldi olinadi."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM products WHERE shop_id = ? AND LOWER(TRIM(name)) = LOWER(TRIM(?))",
            (shop_id, name),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_all_products(shop_id: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM products WHERE shop_id = ? ORDER BY id DESC", (shop_id,)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_products_by_category(shop_id: int, category_id):
    """category_id=None bo'lsa - bo'limga bog'lanmagan (bo'limsiz)
    mahsulotlarni qaytaradi."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await _ensure_category_schema(db)
        if category_id is None:
            cursor = await db.execute(
                "SELECT * FROM products WHERE shop_id = ? AND category_id IS NULL ORDER BY id DESC",
                (shop_id,),
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM products WHERE shop_id = ? AND category_id = ? ORDER BY id DESC",
                (shop_id, category_id),
            )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def search_products(shop_id: int, query: str):
    """Mahsulot nomi bo'yicha qidiradi (nom ichida qidiruv so'zi uchrasa yetarli,
    katta-kichik harfga qaramaydi)."""
    query = (query or "").strip()
    if not query:
        return []
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM products WHERE shop_id = ? AND LOWER(name) LIKE LOWER(?) ORDER BY name",
            (shop_id, f"%{query}%"),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


# ---------- BO'LIMLAR ----------
# Erkin tuzilma - do'kon egasi (yoki sotuvchi) xohlagancha bo'lim yaratishi
# mumkin, mahsulot bo'limga bog'lanishi shart emas.

async def add_category(shop_id: int, name: str):
    """Bir xil nomli bo'lim (katta-kichik harf/bo'sh joydan qat'i nazar)
    ikki marta yaratilmasligi uchun avval mavjudligini tekshiradi."""
    name = name.strip()
    existing = await find_category_by_name(shop_id, name)
    if existing:
        return existing
    async with aiosqlite.connect(config.DB_PATH) as db:
        await _ensure_category_schema(db)
        cursor = await db.execute(
            "INSERT INTO categories (shop_id, name, created_at) VALUES (?, ?, ?)",
            (shop_id, name, _now()),
        )
        await db.commit()
        return {"id": cursor.lastrowid, "shop_id": shop_id, "name": name}


async def find_category_by_name(shop_id: int, name: str):
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await _ensure_category_schema(db)
        cursor = await db.execute(
            "SELECT * FROM categories WHERE shop_id = ? AND LOWER(TRIM(name)) = LOWER(TRIM(?))",
            (shop_id, name),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_category(shop_id: int, category_id: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await _ensure_category_schema(db)
        cursor = await db.execute(
            "SELECT * FROM categories WHERE id = ? AND shop_id = ?", (category_id, shop_id)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_categories(shop_id: int):
    """Har bir bo'limni ichidagi mahsulotlar sonini (product_count) bilan qaytaradi."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await _ensure_category_schema(db)
        cursor = await db.execute(
            "SELECT c.id, c.shop_id, c.name, c.created_at, "
            "COUNT(p.id) AS product_count "
            "FROM categories c "
            "LEFT JOIN products p ON p.category_id = c.id AND p.shop_id = c.shop_id "
            "WHERE c.shop_id = ? "
            "GROUP BY c.id "
            "ORDER BY c.name COLLATE NOCASE ASC",
            (shop_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_uncategorized_count(shop_id: int) -> int:
    async with aiosqlite.connect(config.DB_PATH) as db:
        await _ensure_category_schema(db)
        cursor = await db.execute(
            "SELECT COUNT(*) FROM products WHERE shop_id = ? AND category_id IS NULL",
            (shop_id,),
        )
        return (await cursor.fetchone())[0]


async def set_product_category(shop_id: int, product_id: int, category_id) -> bool:
    """Mahsulotni boshqa bo'limga ko'chiradi yoki bo'limdan chiqaradi
    (category_id=None bo'lsa - bo'limsiz holatga o'tadi). category_id berilgan
    bo'lsa, avval o'sha bo'lim shu do'konga tegishli ekanini tekshiradi."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        await _ensure_category_schema(db)
        if category_id is not None:
            cursor = await db.execute(
                "SELECT 1 FROM categories WHERE id = ? AND shop_id = ?", (category_id, shop_id)
            )
            if not await cursor.fetchone():
                return False
        cursor = await db.execute(
            "UPDATE products SET category_id = ? WHERE id = ? AND shop_id = ?",
            (category_id, product_id, shop_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def delete_category(shop_id: int, category_id: int) -> bool:
    """Bo'limni o'chiradi - ichidagi mahsulotlar o'chmaydi, faqat
    bo'limsiz holatga o'tadi."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        await _ensure_category_schema(db)
        await db.execute(
            "UPDATE products SET category_id = NULL WHERE category_id = ? AND shop_id = ?",
            (category_id, shop_id),
        )
        cursor = await db.execute(
            "DELETE FROM categories WHERE id = ? AND shop_id = ?", (category_id, shop_id)
        )
        await db.commit()
        return cursor.rowcount > 0


# ---------- FILIALLAR ----------
# Do'kon egasi o'zining bir nechta jismoniy filialini (do'kon nuqtasini)
# qo'sha oladi. Har bir filial faqat shu do'konga (shop_id) tegishli -
# boshqa do'kon egasi bu filiallarni ko'rmaydi/boshqara olmaydi.

async def _ensure_branch_schema(db):
    """Himoya chorasi: agar biror sababdan init_db() hali filiallar
    sxemasini yaratmagan bo'lsa (masalan eski jarayon hali qayta ishga
    tushmagan bo'lsa), har bir filial bilan ishlaydigan funksiya
    chaqirilganda sxema shu yerda ham xavfsiz tarzda yaratiladi."""
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS branches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            address TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    await db.commit()


async def add_branch(shop_id: int, name: str, address: str = None):
    """Bir xil nomli filial (katta-kichik harf/bo'sh joydan qat'i nazar)
    ikki marta yaratilmasligi uchun avval mavjudligini tekshiradi."""
    name = name.strip()
    existing = await find_branch_by_name(shop_id, name)
    if existing:
        return existing
    async with aiosqlite.connect(config.DB_PATH) as db:
        await _ensure_branch_schema(db)
        cursor = await db.execute(
            "INSERT INTO branches (shop_id, name, address, created_at) VALUES (?, ?, ?, ?)",
            (shop_id, name, address, _now()),
        )
        await db.commit()
        return {"id": cursor.lastrowid, "shop_id": shop_id, "name": name, "address": address}


async def find_branch_by_name(shop_id: int, name: str):
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await _ensure_branch_schema(db)
        cursor = await db.execute(
            "SELECT * FROM branches WHERE shop_id = ? AND LOWER(TRIM(name)) = LOWER(TRIM(?))",
            (shop_id, name),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_branch(shop_id: int, branch_id: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await _ensure_branch_schema(db)
        cursor = await db.execute(
            "SELECT * FROM branches WHERE id = ? AND shop_id = ?", (branch_id, shop_id)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_branches(shop_id: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await _ensure_branch_schema(db)
        cursor = await db.execute(
            "SELECT * FROM branches WHERE shop_id = ? ORDER BY name COLLATE NOCASE ASC",
            (shop_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def delete_branch(shop_id: int, branch_id: int) -> bool:
    async with aiosqlite.connect(config.DB_PATH) as db:
        await _ensure_branch_schema(db)
        cursor = await db.execute(
            "DELETE FROM branches WHERE id = ? AND shop_id = ?", (branch_id, shop_id)
        )
        deleted = cursor.rowcount > 0
        if deleted:
            # O'chirilgan filial hozir "joriy" bo'lsa, egasini "Bosh filial"ga qaytaramiz.
            await db.execute(
                "UPDATE owners SET current_branch_id = NULL "
                "WHERE telegram_id = ? AND current_branch_id = ?",
                (shop_id, branch_id),
            )
            # Shu filialga biriktirilgan sotuvchilarni ham "Bosh filial"ga o'tkazamiz -
            # aks holda o'chirilgan filialga "osilib qolishardi".
            await db.execute(
                "UPDATE sellers SET branch_id = NULL WHERE shop_id = ? AND branch_id = ?",
                (shop_id, branch_id),
            )
        await db.commit()
        return deleted


async def set_owner_current_branch(telegram_id: int, branch_id):
    """Do'kon egasining joriy filialini almashtiradi. branch_id=None bo'lsa,
    "Bosh filial" (filialsiz) holatiga qaytaradi."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "UPDATE owners SET current_branch_id = ? WHERE telegram_id = ?",
            (branch_id, telegram_id),
        )
        await db.commit()


async def delete_product(shop_id: int, product_id: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "DELETE FROM products WHERE id = ? AND shop_id = ?", (product_id, shop_id)
        )
        await db.commit()


async def mark_product_sold(shop_id: int, product_id: int):
    """Mahsulot sotilganda chaqiriladi - 'oxirgi marta qachon sotilgan' vaqtini yangilaydi."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "UPDATE products SET last_sold_at = ? WHERE id = ? AND shop_id = ?",
            (_now(), product_id, shop_id),
        )
        await db.commit()


async def get_stale_products(shop_id: int, days: int = 30):
    """Skladda bor, lekin oxirgi `days` kun ichida sotilmagan (yoki umuman
    sotilmagan va shuncha vaqtdan beri turgan) mahsulotlar. Eng uzoq
    turganidan boshlab tartiblanadi."""
    cutoff = datetime.now() - timedelta(days=days)
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM products WHERE shop_id = ? AND quantity > 0", (shop_id,)
        )
        rows = [dict(row) for row in await cursor.fetchall()]

    stale = []
    for p in rows:
        reference = p.get("last_sold_at") or p.get("created_at")
        try:
            reference_dt = datetime.strptime(reference, "%Y-%m-%d %H:%M:%S")
        except (TypeError, ValueError):
            continue
        if reference_dt <= cutoff:
            p["reference_date"] = reference
            stale.append(p)

    stale.sort(key=lambda p: p["reference_date"])
    return stale


# ---------- OLINISHI KERAK BO'LGAN TOVARLAR ----------

async def get_low_stock_products(shop_id: int):
    """Xodim belgilagan ogohlantirish chegarasidan kam qolgan mahsulotlar."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM products WHERE shop_id = ? AND alert_quantity IS NOT NULL "
            "AND quantity <= alert_quantity ORDER BY quantity ASC",
            (shop_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def add_manual_restock_item(shop_id: int, name: str, note: str = None):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "INSERT INTO restock_manual (shop_id, name, note, created_at) VALUES (?, ?, ?, ?)",
            (shop_id, name, note, _now()),
        )
        await db.commit()


async def get_manual_restock_items(shop_id: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM restock_manual WHERE shop_id = ? ORDER BY id DESC", (shop_id,)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_manual_restock_item(shop_id: int, item_id: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM restock_manual WHERE id = ? AND shop_id = ?", (item_id, shop_id)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def delete_manual_restock_item(shop_id: int, item_id: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "DELETE FROM restock_manual WHERE id = ? AND shop_id = ?", (item_id, shop_id)
        )
        await db.commit()


# ---------- KIRIM / CHIQIM (TRANSAKSIYALAR) ----------

async def add_transaction(shop_id: int, type_: str, amount: float, description: str,
                           payment_method: str = None, performed_by: int = None, branch_id=None):
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO transactions (shop_id, type, amount, description, created_at, payment_method, "
            "performed_by, branch_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (shop_id, type_, amount, description, _now(), payment_method, performed_by, branch_id),
        )
        await db.commit()
        return cursor.lastrowid


async def get_payment_method_totals(shop_id: int, type_: str = "income", branch_id=None):
    """Naqd va plastik bo'yicha jami summalarni qaytaradi (masalan savdo hisobotida).

    branch_id - filial bo'yicha hisobot uchun (None=barcha, 0=Bosh filial, <id>=shu filial)."""
    clause, extra = _branch_filter(branch_id)
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            f"SELECT COALESCE(SUM(amount), 0) FROM transactions "
            f"WHERE shop_id=? AND type=? AND payment_method='naqd'{clause}",
            [shop_id, type_] + extra,
        )
        naqd = (await cursor.fetchone())[0]
        cursor = await db.execute(
            f"SELECT COALESCE(SUM(amount), 0) FROM transactions "
            f"WHERE shop_id=? AND type=? AND payment_method='plastik'{clause}",
            [shop_id, type_] + extra,
        )
        plastik = (await cursor.fetchone())[0]
        return {"naqd": naqd, "plastik": plastik}


async def get_transactions(shop_id: int, limit: int = 1000):
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM transactions WHERE shop_id = ? ORDER BY id DESC LIMIT ?",
            (shop_id, limit),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_totals(shop_id: int, branch_id=None):
    """branch_id - filial bo'yicha hisobot uchun (None=barcha, 0=Bosh filial, <id>=shu filial)."""
    clause, extra = _branch_filter(branch_id)
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            f"SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE shop_id = ? AND type = 'income'{clause}",
            [shop_id] + extra,
        )
        income = (await cursor.fetchone())[0]

        cursor = await db.execute(
            f"SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE shop_id = ? AND type = 'expense'{clause}",
            [shop_id] + extra,
        )
        expense = (await cursor.fetchone())[0]

        return income, expense


# ---------- SAVDO TARKIBI / BOG'LAB SOTISH (CROSS-SELL) ----------

async def add_sale_item(shop_id: int, sale_id: int, product_id: int, quantity: float, price: float,
                         performed_by: int = None):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "INSERT INTO sale_items (shop_id, sale_id, product_id, quantity, price, created_at, "
            "performed_by) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (shop_id, sale_id, product_id, quantity, price, _now(), performed_by),
        )
        await db.commit()


async def get_cross_sell_suggestions(shop_id: int, product_ids, exclude_ids=None, limit: int = 3):
    """Berilgan mahsulot(lar) bilan tarixda eng ko'p birga sotilgan,
    hozir skladda bor va savatchada hali yo'q mahsulotlarni qaytaradi (shu do'kon ichida)."""
    if not product_ids:
        return []
    exclude_ids = set(exclude_ids or []) | set(product_ids)

    placeholders = ",".join("?" for _ in product_ids)
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            f"""
            SELECT other.product_id AS product_id, COUNT(*) AS times
            FROM sale_items base
            JOIN sale_items other
              ON other.sale_id = base.sale_id AND other.product_id != base.product_id
            WHERE base.shop_id = ? AND other.shop_id = ? AND base.product_id IN ({placeholders})
            GROUP BY other.product_id
            ORDER BY times DESC
            """,
            [shop_id, shop_id] + list(product_ids),
        )
        rows = await cursor.fetchall()

        suggestions = []
        for row in rows:
            if row["product_id"] in exclude_ids:
                continue
            product = await get_product(shop_id, row["product_id"])
            if not product or product["quantity"] <= 0:
                continue
            suggestions.append({"product": product, "times": row["times"]})
            exclude_ids.add(row["product_id"])
            if len(suggestions) >= limit:
                break

        return suggestions


async def search_sales(shop_id: int, query: str, limit: int = 30):
    """Mahsulot nomi bo'yicha savdolarni qidiradi (eng yangisidan boshlab).

    Har bir natija - bitta savdo chekidagi bitta qatordan (mahsulot),
    lekin bir xil sale_id (chek)dagi qatorlar chaqiruvchi tomonda birlashtiriladi.
    Mahsulot o'chirilgan bo'lsa (products'da qolmagan), shu qator natijaga
    tushmaydi - faqat hozircha mavjud mahsulotlar bo'yicha qidiriladi.
    """
    like_query = f"%{query.strip().lower()}%"
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT si.sale_id, si.quantity, si.price, p.name AS product_name,
                   t.created_at, t.payment_method
            FROM sale_items si
            JOIN products p ON p.id = si.product_id AND p.shop_id = si.shop_id
            JOIN transactions t ON t.id = si.sale_id AND t.shop_id = si.shop_id
            WHERE si.shop_id = ? AND LOWER(p.name) LIKE ?
            ORDER BY si.sale_id DESC, si.id ASC
            LIMIT ?
            """,
            (shop_id, like_query, limit),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


# ---------- FOYDALANUVCHILAR (DO'KON EGALARI) ----------

async def get_top_selling_products(shop_id: int, limit: int = 10, branch_id=None):
    """branch_id - filial bo'yicha kesim uchun (None=barcha, 0=Bosh filial, <id>=shu filial).

    sale_items'da branch_id yo'q, shuning uchun har bir savdo chekining
    filialini bog'liq transactions yozuvidan (t.branch_id) olamiz."""
    clause, extra = _branch_filter(branch_id, column="t.branch_id")
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            f"""
            SELECT p.name AS name, SUM(si.quantity) AS total_qty,
                   SUM(si.quantity * si.price) AS total_sum
            FROM sale_items si
            JOIN products p ON p.id = si.product_id
            JOIN transactions t ON t.id = si.sale_id AND t.shop_id = si.shop_id
            WHERE si.shop_id = ?{clause}
            GROUP BY si.product_id
            ORDER BY total_qty DESC
            LIMIT ?
            """,
            [shop_id] + extra + [limit],
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_top_profit_products(shop_id: int, limit: int = 10, branch_id=None):
    """branch_id - filial bo'yicha kesim uchun (None=barcha, 0=Bosh filial, <id>=shu filial)."""
    clause, extra = _branch_filter(branch_id, column="t.branch_id")
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            f"""
            SELECT p.name AS name,
                   SUM((si.price - p.price) * si.quantity) AS total_profit
            FROM sale_items si
            JOIN products p ON p.id = si.product_id
            JOIN transactions t ON t.id = si.sale_id AND t.shop_id = si.shop_id
            WHERE si.shop_id = ?{clause}
            GROUP BY si.product_id
            ORDER BY total_profit DESC
            LIMIT ?
            """,
            [shop_id] + extra + [limit],
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def add_owner(telegram_id: int, full_name: str = None, username: str = None,
                     added_by: int = None):
    """Yangi do'kon egasi qo'shiladi va SUBSCRIPTION_TRIAL_DAYS kunlik bepul
    sinov muddati bilan boshlanadi (bosh admin qo'lda qo'shsa ham, o'zi
    ro'yxatdan o'tsa ham - farqi yo'q, har doim trialdan boshlanadi)."""
    trial_until = (datetime.now() + timedelta(days=SUBSCRIPTION_TRIAL_DAYS)).strftime("%Y-%m-%d")
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO owners (telegram_id, full_name, username, added_by, created_at, "
            "subscription_status, subscription_until, trial_used) "
            "VALUES (?, ?, ?, ?, ?, 'trial', ?, 1)",
            (telegram_id, full_name, username, added_by, _now(), trial_until),
        )
        await db.commit()


async def remove_owner(telegram_id: int) -> bool:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute("DELETE FROM owners WHERE telegram_id = ?", (telegram_id,))
        await db.commit()
        return cursor.rowcount > 0


async def get_owners():
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM owners ORDER BY id DESC")
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_owner(telegram_id: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM owners WHERE telegram_id = ?", (telegram_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def set_owner_profile(telegram_id: int, owner_name: str, shop_name: str, phone_number: str = None):
    """Do'kon egasi o'zi haqida va do'koni haqida kiritgan ma'lumotlarni saqlaydi
    (birinchi /start bosganda so'raladigan qisqa so'rovnoma - bosh admin uchun
    do'konlarni bir-biridan ajratib ko'rish maqsadida)."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "UPDATE owners SET owner_name = ?, shop_name = ?, phone_number = ? WHERE telegram_id = ?",
            (owner_name, shop_name, phone_number, telegram_id),
        )
        await db.commit()


async def get_owner_ids():
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute("SELECT telegram_id FROM owners")
        rows = await cursor.fetchall()
        return [row[0] for row in rows]


async def is_owner(telegram_id: int) -> bool:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute("SELECT 1 FROM owners WHERE telegram_id = ?", (telegram_id,))
        row = await cursor.fetchone()
        return row is not None


# ---------- BIR MARTALIK TAKLIF LINKLARI ----------

async def create_owner_invite(created_by: int) -> str:
    """Yangi bir martalik taklif tokeni yaratadi va qaytaradi.
    Token faqat bitta marta, bitta odam tomonidan ishlatilishi mumkin."""
    token = secrets.token_urlsafe(12)  # URL/deep-link uchun xavfsiz belgilar
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "INSERT INTO owner_invites (token, created_by, created_at) VALUES (?, ?, ?)",
            (token, created_by, _now()),
        )
        await db.commit()
    return token


async def get_owner_invite(token: str):
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM owner_invites WHERE token = ?", (token,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def use_owner_invite(token: str, used_by: int) -> bool:
    """Tokenni 'ishlatilgan' deb belgilaydi - lekin faqat u hali ishlatilmagan
    bo'lsa (used_by IS NULL). Shu tekshiruv orqali 2 kishi bir vaqtda bir xil
    linkni bosib qolsa ham, faqat biri muvaffaqiyatli bo'ladi (race-safe)."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE owner_invites SET used_by = ?, used_at = ? "
            "WHERE token = ? AND used_by IS NULL",
            (used_by, _now(), token),
        )
        await db.commit()
        return cursor.rowcount > 0


# ---------- 7-BOSQICH: TO'LOVLARNI QO'LDA TASDIQLASH ----------

async def create_payment(owner_id: int, amount: float, plan: str, days: int,
                          screenshot_file_id: str = None) -> int:
    """Ega chek skrinshotini yuborganda yaratiladigan "kutilayotgan" to'lov
    yozuvi. Hali hech narsani o'zgartirmaydi (obuna uzaytirilmaydi) - faqat
    bosh admin tasdiqlashini (approve_payment) yoki rad etishini
    (reject_payment) kutadi. Qaytadi: yangi yozuvning id'si."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO payments (owner_id, amount, plan, days, method, status, "
            "screenshot_file_id, created_at) VALUES (?, ?, ?, ?, 'qolda', 'pending', ?, ?)",
            (owner_id, amount, plan, days, screenshot_file_id, _now()),
        )
        await db.commit()
        return cursor.lastrowid


async def get_payment(payment_id: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM payments WHERE id = ?", (payment_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def approve_payment(payment_id: int, decided_by: int):
    """To'lovni tasdiqlaydi: payments.status='approved' qilib belgilaydi va
    owners.subscription_until'ni shu to'lovning "days" qiymatiga qarab
    uzaytiradi.

    Kunlar YO'QOTILMASLIGI uchun: agar ega hali FAOL obunaga ega bo'lsa
    (masalan muddati tugashiga bir necha kun qolganda oldindan to'lasa),
    yangi kunlar mavjud subscription_until'ning USTIGA qo'shiladi; aks
    holda (obuna allaqachon tugagan/trialda) bugungi kundan boshlab
    hisoblanadi.

    Allaqachon hal qilingan (approved/rejected) to'lovni qayta tasdiqlamaydi
    - bunday holda None qaytaradi (ikki marta bosilib qolishning oldini
    olish uchun)."""
    payment = await get_payment(payment_id)
    if not payment or payment["status"] != "pending":
        return None

    owner = await get_owner(payment["owner_id"])
    if not owner:
        return None

    today = datetime.now().date()
    base_date = today
    current_until = owner.get("subscription_until")
    if current_until:
        try:
            parsed_until = datetime.strptime(current_until, "%Y-%m-%d").date()
            if parsed_until > today:
                base_date = parsed_until
        except (TypeError, ValueError):
            pass

    new_until = (base_date + timedelta(days=payment["days"] or 0)).strftime("%Y-%m-%d")

    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "UPDATE payments SET status = 'approved', decided_by = ?, decided_at = ? WHERE id = ?",
            (decided_by, _now(), payment_id),
        )
        await db.execute(
            "UPDATE owners SET subscription_status = 'active', subscription_until = ? "
            "WHERE telegram_id = ?",
            (new_until, payment["owner_id"]),
        )
        await db.commit()

    payment["status"] = "approved"
    payment["new_subscription_until"] = new_until
    return payment


async def reject_payment(payment_id: int, decided_by: int, comment: str = None):
    """To'lovni rad etadi - obunaga HECH QANDAY ta'sir qilmaydi, faqat
    yozuvni "rejected" deb belgilaydi (owner qayta chek yuborishi mumkin)."""
    payment = await get_payment(payment_id)
    if not payment or payment["status"] != "pending":
        return None
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "UPDATE payments SET status = 'rejected', decided_by = ?, decided_at = ?, comment = ? "
            "WHERE id = ?",
            (decided_by, _now(), comment, payment_id),
        )
        await db.commit()
    payment["status"] = "rejected"
    return payment


async def get_pending_payments():
    """Bosh admin panelidagi "💳 Kutilayotgan to'lovlar" ro'yxati uchun
    (9-bosqichda ulanadi) - hozircha kod ichida tayyorlab qo'yamiz."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM payments WHERE status = 'pending' ORDER BY id ASC"
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


# ---------- 9-BOSQICH: ADMIN PANELIDAN OBUNANI QO'LDA BOSHQARISH ----------

async def extend_owner_subscription(telegram_id: int, days: int) -> str | None:
    """Bosh admin do'kon egalari ro'yxatidan "➕ Uzaytirish" orqali qo'lda
    obuna qo'shadi (+30/+90/+365 yoki erkin kun soni) - to'lov chekisiz,
    to'g'ridan-to'g'ri. approve_payment() dagi bir xil mantiq: agar ega hali
    FAOL muddatga ega bo'lsa, kunlar mavjud subscription_until USTIGA
    qo'shiladi (yo'qotilmaydi), aks holda bugungi kundan boshlab hisoblanadi.

    Bloklangan bo'lsa ham shu funksiya orqali uzaytirilsa, avtomatik ravishda
    blokdan chiqariladi ('active' qilib belgilanadi) - aks holda kunlar
    qo'shilgani bilan kirish hali taqiqlangan bo'lib qolardi.

    Ega topilmasa - None, aks holda yangi subscription_until (YYYY-MM-DD)
    qaytaradi."""
    owner = await get_owner(telegram_id)
    if not owner:
        return None

    today = datetime.now().date()
    base_date = today
    current_until = owner.get("subscription_until")
    if current_until:
        try:
            parsed_until = datetime.strptime(current_until, "%Y-%m-%d").date()
            if parsed_until > today:
                base_date = parsed_until
        except (TypeError, ValueError):
            pass

    new_until = (base_date + timedelta(days=days)).strftime("%Y-%m-%d")
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "UPDATE owners SET subscription_status = 'active', subscription_until = ? "
            "WHERE telegram_id = ?",
            (new_until, telegram_id),
        )
        await db.commit()
    return new_until


async def set_owner_blocked(telegram_id: int, blocked: bool) -> bool:
    """Bosh admin "🚫 Majburiy bloklash" / "✅ Blokdan chiqarish" tugmasi.

    blocked=True - subscription_status='blocked' qilib belgilaydi: bu holat
    grace period'ga ham qaramaydi, ega (va uning sotuvchilari) darhol botga
    kira olmay qoladi (access_control.compute_subscription_access).

    blocked=False - 'active' holatiga qaytaradi (subscription_until
    o'zgarmaydi) - agar muddat hali o'tmagan bo'lsa darhol qayta kirish
    imkoni tiklanadi, o'tgan bo'lsa oddiy "muddati tugagan" holatiga
    (grace/bloklash ekrani) qaytadi.

    Ega topilmasa - False."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE owners SET subscription_status = ? WHERE telegram_id = ?",
            ("blocked" if blocked else "active", telegram_id),
        )
        await db.commit()
        return cursor.rowcount > 0


# ---------- QARZDORLAR ----------

async def add_debt(shop_id: int, customer_name: str, phone: str, amount: float, description: str,
                    due_date: str = None, taken_date: str = None, performed_by: int = None, branch_id=None):
    if not taken_date:
        taken_date = _now()[:10]  # ustoz/sotuvchi belgilamasa - bugungi sana
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO debts (shop_id, customer_name, phone, amount, description, is_paid, "
            "created_at, due_date, taken_date, performed_by, branch_id) VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?)",
            (shop_id, customer_name, phone, amount, description, _now(), due_date, taken_date, performed_by, branch_id),
        )
        await db.commit()
        return cursor.lastrowid


async def get_debt(shop_id: int, debt_id: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM debts WHERE id = ? AND shop_id = ?", (debt_id, shop_id)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_debt_by_id(debt_id: int):
    """Shop_id talab qilmasdan qarzni topadi - faqat mijoz shaxsiy link orqali
    botni ochganda ishlatiladi (o'sha vaqtda hali shop_id noma'lum, mijozning
    o'zi hech qanday do'konga a'zo emas)."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM debts WHERE id = ?", (debt_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def link_debt_customer(debt_id: int, chat_id: int, username: str = None):
    """Mijoz shaxsiy link orqali botni ochganda uning chat_id/username'ini
    shu qarz yozuviga bog'laydi (keyin unga to'g'ridan-to'g'ri eslatma yuborish uchun)."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "UPDATE debts SET customer_chat_id = ?, customer_username = ? WHERE id = ?",
            (chat_id, username, debt_id),
        )
        await db.commit()


async def get_debts(shop_id: int, only_unpaid: bool = True):
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if only_unpaid:
            cursor = await db.execute(
                "SELECT * FROM debts WHERE shop_id = ? AND is_paid = 0 ORDER BY id DESC",
                (shop_id,),
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM debts WHERE shop_id = ? ORDER BY id DESC", (shop_id,)
            )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_total_debt(shop_id: int, branch_id=None):
    """branch_id - filial bo'yicha hisobot uchun (None=barcha, 0=Bosh filial, <id>=shu filial)."""
    clause, extra = _branch_filter(branch_id)
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COALESCE(SUM(amount - paid_amount), 0) FROM debts "
            f"WHERE shop_id = ? AND is_paid = 0{clause}",
            [shop_id] + extra,
        )
        return (await cursor.fetchone())[0]


async def get_overdue_debts(shop_id: int, days: int = 3):
    """To'lanmagan qarzlar orasidan muddati o'tganlarini qaytaradi - eng eskisidan boshlab.

    Agar qarzda aniq qaytarish sanasi (due_date) belgilangan bo'lsa, o'sha sanadan
    o'tgan qarzlar "muddati o'tgan" hisoblanadi. due_date belgilanmagan qarzlar uchun
    eski qoida ishlaydi: yaratilganidan `days` kun o'tgan bo'lsa, muddati o'tgan deb
    hisoblanadi.
    """
    now = datetime.now()
    cutoff = now - timedelta(days=days)
    debts = await get_debts(shop_id, only_unpaid=True)
    overdue = []
    for d in debts:
        try:
            created_dt = datetime.strptime(d["created_at"], "%Y-%m-%d %H:%M:%S")
        except (TypeError, ValueError):
            continue

        due_date_str = d.get("due_date")
        if due_date_str:
            try:
                due_dt = datetime.strptime(due_date_str, "%Y-%m-%d")
            except ValueError:
                due_dt = None
            if due_dt is None or due_dt.date() >= now.date():
                continue
            d["days_ago"] = (now - due_dt).days
        else:
            if created_dt > cutoff:
                continue
            d["days_ago"] = (now - created_dt).days

        overdue.append(d)
    overdue.sort(key=lambda d: d["days_ago"], reverse=True)
    return overdue


async def mark_debt_paid(shop_id: int, debt_id: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "UPDATE debts SET is_paid = 1, paid_amount = amount WHERE id = ? AND shop_id = ?",
            (debt_id, shop_id),
        )
        await db.commit()


async def add_debt_payment(shop_id: int, debt_id: int, amount: float, performed_by: int = None,
                            payment_method: str = None, cash_amount: float = None,
                            card_amount: float = None):
    """Qarzga to'lov qo'shadi - qisman yoki to'liq.
    payment_method: 'naqd' | 'plastik' | 'aralash'. 'aralash' bo'lsa cash_amount/card_amount
    bo'yicha ikkita alohida yozuv sifatida saqlanadi (tarixda naqd/plastik ulushi ko'rinishi uchun).
    Natija: {'status': 'full'|'partial', 'paid_amount': ..., 'remaining': ...} yoki None (qarz topilmasa)."""
    debt = await get_debt(shop_id, debt_id)
    if not debt:
        return None

    current_paid = debt.get("paid_amount") or 0
    new_paid = current_paid + amount
    total = debt["amount"]

    async with aiosqlite.connect(config.DB_PATH) as db:
        if payment_method == "aralash":
            if cash_amount:
                await db.execute(
                    "INSERT INTO debt_payments (debt_id, amount, paid_at, performed_by, payment_method) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (debt_id, cash_amount, _now(), performed_by, "naqd"),
                )
            if card_amount:
                await db.execute(
                    "INSERT INTO debt_payments (debt_id, amount, paid_at, performed_by, payment_method) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (debt_id, card_amount, _now(), performed_by, "plastik"),
                )
        else:
            await db.execute(
                "INSERT INTO debt_payments (debt_id, amount, paid_at, performed_by, payment_method) "
                "VALUES (?, ?, ?, ?, ?)",
                (debt_id, amount, _now(), performed_by, payment_method),
            )
        if new_paid >= total:
            await db.execute(
                "UPDATE debts SET paid_amount = ?, is_paid = 1 WHERE id = ? AND shop_id = ?",
                (total, debt_id, shop_id),
            )
            status = "full"
            new_paid = total
        else:
            await db.execute(
                "UPDATE debts SET paid_amount = ? WHERE id = ? AND shop_id = ?",
                (new_paid, debt_id, shop_id),
            )
            status = "partial"
        await db.commit()

    return {"status": status, "paid_amount": new_paid, "remaining": total - new_paid}


async def get_debt_payments(shop_id: int, debt_id: int):
    """debt_id shu shop_id'ga tegishli ekanini avval tekshiradi (boshqa do'konning
    to'lov tarixi ko'rinib qolmasligi uchun)."""
    debt = await get_debt(shop_id, debt_id)
    if not debt:
        return []
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM debt_payments WHERE debt_id = ? ORDER BY paid_at", (debt_id,)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


# ---------- SOTUVCHILAR ----------
# Har bir sotuvchi bitta do'konga (shop_id = do'kon egasining telegram_id'si)
# tegishli. Faqat shu do'kon egasi o'z sotuvchilarini qo'sha/o'chira oladi
# (handlers/sellers.py buni har doim shop_id bilan tekshiradi).

async def add_seller(telegram_id: int, shop_id: int, full_name: str = None,
                      username: str = None, added_by: int = None, branch_id=None):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO sellers (telegram_id, shop_id, full_name, username, added_by, "
            "branch_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (telegram_id, shop_id, full_name, username, added_by, branch_id, _now()),
        )
        await db.commit()


async def remove_seller(shop_id: int, telegram_id: int) -> bool:
    """shop_id bilan birga tekshiradi - do'kon egasi faqat O'Z sotuvchisini
    o'chira oladi, boshqa do'konning sotuvchisini emas."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM sellers WHERE telegram_id = ? AND shop_id = ?", (telegram_id, shop_id)
        )
        await db.commit()
        return cursor.rowcount > 0


async def set_seller_branch(shop_id: int, telegram_id: int, branch_id) -> bool:
    """Do'kon egasi sotuvchini qo'lda boshqa filialga ko'chiradi.
    branch_id=None bo'lsa - "Bosh filial"ga qaytaradi. shop_id bilan birga
    tekshiriladi - egasi faqat O'Z sotuvchisini ko'chira oladi."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE sellers SET branch_id = ? WHERE telegram_id = ? AND shop_id = ?",
            (branch_id, telegram_id, shop_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_sellers(shop_id: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM sellers WHERE shop_id = ? ORDER BY id DESC", (shop_id,)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def is_seller(telegram_id: int) -> bool:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute("SELECT 1 FROM sellers WHERE telegram_id = ?", (telegram_id,))
        row = await cursor.fetchone()
        return row is not None


async def get_seller_shop_id(telegram_id: int):
    """Sotuvchi qaysi do'konga tegishli ekanini qaytaradi (topilmasa None)."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            "SELECT shop_id FROM sellers WHERE telegram_id = ?", (telegram_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row else None


async def get_seller(telegram_id: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM sellers WHERE telegram_id = ?", (telegram_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def set_seller_profile(telegram_id: int, seller_name: str, phone_number: str = None):
    """Sotuvchi o'zi haqida kiritgan ma'lumotlarni saqlaydi (birinchi /start
    bosganda so'raladigan qisqa so'rovnoma - do'kon egasi uchun sotuvchilarni
    bir-biridan ajratib ko'rish maqsadida)."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "UPDATE sellers SET seller_name = ?, phone_number = ? WHERE telegram_id = ?",
            (seller_name, phone_number, telegram_id),
        )
        await db.commit()


# ---------- SOTUVCHI UCHUN BIR MARTALIK TAKLIF LINKLARI ----------

async def create_seller_invite(shop_id: int, created_by: int, branch_id=None) -> str:
    """Yangi bir martalik sotuvchi taklif tokenini yaratadi (faqat shu do'konga
    tegishli). Token faqat bitta marta, bitta odam tomonidan ishlatilishi mumkin.
    branch_id - link yaratilgan paytdagi egasining joriy filiali; link
    ishlatilib sotuvchi qo'shilganda shu filial sotuvchiga biriktiriladi."""
    token = secrets.token_urlsafe(12)
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "INSERT INTO seller_invites (token, shop_id, created_by, branch_id, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (token, shop_id, created_by, branch_id, _now()),
        )
        await db.commit()
    return token


async def get_seller_invite(token: str):
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM seller_invites WHERE token = ?", (token,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def use_seller_invite(token: str, used_by: int) -> bool:
    """Race-safe: token faqat used_by hali NULL bo'lsa ishlaydi."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE seller_invites SET used_by = ?, used_at = ? WHERE token = ? AND used_by IS NULL",
            (used_by, _now(), token),
        )
        await db.commit()
        return cursor.rowcount > 0
