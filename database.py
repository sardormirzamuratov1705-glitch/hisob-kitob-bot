import os
import secrets
from datetime import datetime, timedelta

import aiosqlite

import config


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

        # Sotuvchining o'zi kiritgan ismi va telefon raqami - do'kon egasi
        # bir nechta sotuvchini boshqarganda ularni Telegram ID/username
        # emas, balki tanish nom bilan bir-biridan ajratib olishi uchun.
        for col in ("seller_name", "phone_number"):
            try:
                await db.execute(f"ALTER TABLE sellers ADD COLUMN {col} TEXT")
            except Exception:
                pass
        await db.commit()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


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
                           payment_method: str = None, performed_by: int = None):
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO transactions (shop_id, type, amount, description, created_at, payment_method, "
            "performed_by) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (shop_id, type_, amount, description, _now(), payment_method, performed_by),
        )
        await db.commit()
        return cursor.lastrowid


async def get_payment_method_totals(shop_id: int, type_: str = "income"):
    """Naqd va plastik bo'yicha jami summalarni qaytaradi (masalan savdo hisobotida)."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions "
            "WHERE shop_id=? AND type=? AND payment_method='naqd'",
            (shop_id, type_),
        )
        naqd = (await cursor.fetchone())[0]
        cursor = await db.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions "
            "WHERE shop_id=? AND type=? AND payment_method='plastik'",
            (shop_id, type_),
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


async def get_totals(shop_id: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE shop_id = ? AND type = 'income'",
            (shop_id,),
        )
        income = (await cursor.fetchone())[0]

        cursor = await db.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE shop_id = ? AND type = 'expense'",
            (shop_id,),
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

async def get_top_selling_products(shop_id: int, limit: int = 10):
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT p.name AS name, SUM(si.quantity) AS total_qty,
                   SUM(si.quantity * si.price) AS total_sum
            FROM sale_items si
            JOIN products p ON p.id = si.product_id
            WHERE si.shop_id = ?
            GROUP BY si.product_id
            ORDER BY total_qty DESC
            LIMIT ?
            """,
            (shop_id, limit),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_top_profit_products(shop_id: int, limit: int = 10):
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT p.name AS name,
                   SUM((si.price - p.price) * si.quantity) AS total_profit
            FROM sale_items si
            JOIN products p ON p.id = si.product_id
            WHERE si.shop_id = ?
            GROUP BY si.product_id
            ORDER BY total_profit DESC
            LIMIT ?
            """,
            (shop_id, limit),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def add_owner(telegram_id: int, full_name: str = None, username: str = None,
                     added_by: int = None):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO owners (telegram_id, full_name, username, added_by, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (telegram_id, full_name, username, added_by, _now()),
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


# ---------- QARZDORLAR ----------

async def add_debt(shop_id: int, customer_name: str, phone: str, amount: float, description: str,
                    due_date: str = None, taken_date: str = None, performed_by: int = None):
    if not taken_date:
        taken_date = _now()[:10]  # ustoz/sotuvchi belgilamasa - bugungi sana
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO debts (shop_id, customer_name, phone, amount, description, is_paid, "
            "created_at, due_date, taken_date, performed_by) VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?)",
            (shop_id, customer_name, phone, amount, description, _now(), due_date, taken_date, performed_by),
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


async def get_total_debt(shop_id: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COALESCE(SUM(amount - paid_amount), 0) FROM debts "
            "WHERE shop_id = ? AND is_paid = 0",
            (shop_id,),
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


async def add_debt_payment(shop_id: int, debt_id: int, amount: float, performed_by: int = None):
    """Qarzga to'lov qo'shadi - qisman yoki to'liq.
    Natija: {'status': 'full'|'partial', 'paid_amount': ..., 'remaining': ...} yoki None (qarz topilmasa)."""
    debt = await get_debt(shop_id, debt_id)
    if not debt:
        return None

    current_paid = debt.get("paid_amount") or 0
    new_paid = current_paid + amount
    total = debt["amount"]

    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "INSERT INTO debt_payments (debt_id, amount, paid_at, performed_by) VALUES (?, ?, ?, ?)",
            (debt_id, amount, _now(), performed_by),
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
                      username: str = None, added_by: int = None):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO sellers (telegram_id, shop_id, full_name, username, added_by, "
            "created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (telegram_id, shop_id, full_name, username, added_by, _now()),
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

async def create_seller_invite(shop_id: int, created_by: int) -> str:
    """Yangi bir martalik sotuvchi taklif tokenini yaratadi (faqat shu do'konga
    tegishli). Token faqat bitta marta, bitta odam tomonidan ishlatilishi mumkin."""
    token = secrets.token_urlsafe(12)
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "INSERT INTO seller_invites (token, shop_id, created_by, created_at) VALUES (?, ?, ?, ?)",
            (token, shop_id, created_by, _now()),
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
