import os
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
        ]:
            try:
                await db.execute(f"ALTER TABLE products ADD COLUMN {column} {col_type}")
            except Exception:
                pass
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                amount REAL NOT NULL,
                description TEXT,
                created_at TEXT NOT NULL,
                payment_method TEXT
            )
            """
        )
        try:
            await db.execute("ALTER TABLE transactions ADD COLUMN payment_method TEXT")
        except Exception:
            pass
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS restock_manual (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                note TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS debts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                sale_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                quantity REAL NOT NULL,
                price REAL NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        # Do'kon egalari (bosh admin tomonidan bot orqali qo'shiladigan foydalanuvchilar).
        # Bosh admin - config.ADMIN_IDS (.env), faqat shu ro'yxatdagilar bu jadvalga
        # yozuv qo'sha/o'chira oladi. Bu yerga qo'shilganlar boshqa hamma bo'limga
        # (Sklad, Kirim/Chiqim, Qarz daftar, Hisobot) to'liq kirishi mumkin, lekin
        # "Foydalanuvchilar" bo'limini ko'rmaydi/ishlata olmaydi.
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
        await db.commit()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------- MAHSULOTLAR (SKLAD) ----------

async def add_product(name: str, price: float, quantity: float, photo_file_id,
                       channel_message_id=None, sell_price=None, min_price=None,
                       alert_quantity=None):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "INSERT INTO products (name, price, quantity, photo_file_id, channel_message_id, "
            "sell_price, min_price, alert_quantity, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (name, price, quantity, photo_file_id, channel_message_id, sell_price, min_price,
             alert_quantity, _now()),
        )
        await db.commit()


async def get_product(product_id: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def update_product_quantity(product_id: int, quantity: float):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "UPDATE products SET quantity = ? WHERE id = ?", (quantity, product_id)
        )
        await db.commit()


async def update_product_purchase(product_id: int, add_quantity: float,
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
        cursor = await db.execute("SELECT quantity, price FROM products WHERE id = ?", (product_id,))
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
            "alert_quantity = ? WHERE id = ?",
            (new_quantity, weighted_price, sell_price, min_price, alert_quantity, product_id),
        )
        await db.commit()
        return new_quantity, weighted_price


async def get_all_products():
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM products ORDER BY id DESC")
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def delete_product(product_id: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("DELETE FROM products WHERE id = ?", (product_id,))
        await db.commit()


async def mark_product_sold(product_id: int):
    """Mahsulot sotilganda chaqiriladi - 'oxirgi marta qachon sotilgan' vaqtini yangilaydi."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "UPDATE products SET last_sold_at = ? WHERE id = ?", (_now(), product_id)
        )
        await db.commit()


async def get_stale_products(days: int = 30):
    """Skladda bor, lekin oxirgi `days` kun ichida sotilmagan (yoki umuman
    sotilmagan va shuncha vaqtdan beri turgan) mahsulotlar. Eng uzoq
    turganidan boshlab tartiblanadi."""
    cutoff = datetime.now() - timedelta(days=days)
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM products WHERE quantity > 0")
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

async def get_low_stock_products():
    """Xodim belgilagan ogohlantirish chegarasidan kam qolgan mahsulotlar."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM products WHERE alert_quantity IS NOT NULL "
            "AND quantity <= alert_quantity ORDER BY quantity ASC"
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def add_manual_restock_item(name: str, note: str = None):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "INSERT INTO restock_manual (name, note, created_at) VALUES (?, ?, ?)",
            (name, note, _now()),
        )
        await db.commit()


async def get_manual_restock_items():
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM restock_manual ORDER BY id DESC")
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_manual_restock_item(item_id: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM restock_manual WHERE id = ?", (item_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def delete_manual_restock_item(item_id: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("DELETE FROM restock_manual WHERE id = ?", (item_id,))
        await db.commit()


# ---------- KIRIM / CHIQIM (TRANSAKSIYALAR) ----------

async def add_transaction(type_: str, amount: float, description: str, payment_method: str = None):
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO transactions (type, amount, description, created_at, payment_method) "
            "VALUES (?, ?, ?, ?, ?)",
            (type_, amount, description, _now(), payment_method),
        )
        await db.commit()
        return cursor.lastrowid


async def get_payment_method_totals(type_: str = "income"):
    """Naqd va plastik bo'yicha jami summalarni qaytaradi (masalan savdo hisobotida)."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type=? AND payment_method='naqd'",
            (type_,),
        )
        naqd = (await cursor.fetchone())[0]
        cursor = await db.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type=? AND payment_method='plastik'",
            (type_,),
        )
        plastik = (await cursor.fetchone())[0]
        return {"naqd": naqd, "plastik": plastik}


async def get_transactions(limit: int = 1000):
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM transactions ORDER BY id DESC LIMIT ?", (limit,)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_totals():
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type = 'income'"
        )
        income = (await cursor.fetchone())[0]

        cursor = await db.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type = 'expense'"
        )
        expense = (await cursor.fetchone())[0]

        return income, expense


# ---------- SAVDO TARKIBI / BOG'LAB SOTISH (CROSS-SELL) ----------

async def add_sale_item(sale_id: int, product_id: int, quantity: float, price: float):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "INSERT INTO sale_items (sale_id, product_id, quantity, price, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (sale_id, product_id, quantity, price, _now()),
        )
        await db.commit()


async def get_cross_sell_suggestions(product_ids, exclude_ids=None, limit: int = 3):
    """Berilgan mahsulot(lar) bilan tarixda eng ko'p birga sotilgan,
    hozir skladda bor va savatchada hali yo'q mahsulotlarni qaytaradi."""
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
            WHERE base.product_id IN ({placeholders})
            GROUP BY other.product_id
            ORDER BY times DESC
            """,
            list(product_ids),
        )
        rows = await cursor.fetchall()

        suggestions = []
        for row in rows:
            if row["product_id"] in exclude_ids:
                continue
            product = await get_product(row["product_id"])
            if not product or product["quantity"] <= 0:
                continue
            suggestions.append({"product": product, "times": row["times"]})
            exclude_ids.add(row["product_id"])
            if len(suggestions) >= limit:
                break

        return suggestions


# ---------- FOYDALANUVCHILAR (DO'KON EGALARI) ----------

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


# ---------- QARZDORLAR ----------

async def add_debt(customer_name: str, phone: str, amount: float, description: str,
                    due_date: str = None, taken_date: str = None):
    if not taken_date:
        taken_date = _now()[:10]  # ustoz/sotuvchi belgilamasa - bugungi sana
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO debts (customer_name, phone, amount, description, is_paid, created_at, due_date, taken_date) "
            "VALUES (?, ?, ?, ?, 0, ?, ?, ?)",
            (customer_name, phone, amount, description, _now(), due_date, taken_date),
        )
        await db.commit()
        return cursor.lastrowid


async def get_debt(debt_id: int):
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


async def get_debts(only_unpaid: bool = True):
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if only_unpaid:
            cursor = await db.execute(
                "SELECT * FROM debts WHERE is_paid = 0 ORDER BY id DESC"
            )
        else:
            cursor = await db.execute("SELECT * FROM debts ORDER BY id DESC")
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_total_debt():
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COALESCE(SUM(amount - paid_amount), 0) FROM debts WHERE is_paid = 0"
        )
        return (await cursor.fetchone())[0]


async def get_overdue_debts(days: int = 3):
    """To'lanmagan qarzlar orasidan muddati o'tganlarini qaytaradi - eng eskisidan boshlab.

    Agar qarzda aniq qaytarish sanasi (due_date) belgilangan bo'lsa, o'sha sanadan
    o'tgan qarzlar "muddati o'tgan" hisoblanadi. due_date belgilanmagan qarzlar uchun
    eski qoida ishlaydi: yaratilganidan `days` kun o'tgan bo'lsa, muddati o'tgan deb
    hisoblanadi.
    """
    now = datetime.now()
    cutoff = now - timedelta(days=days)
    debts = await get_debts(only_unpaid=True)
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


async def mark_debt_paid(debt_id: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "UPDATE debts SET is_paid = 1, paid_amount = amount WHERE id = ?", (debt_id,)
        )
        await db.commit()


async def add_debt_payment(debt_id: int, amount: float):
    """Qarzga to'lov qo'shadi - qisman yoki to'liq.
    Natija: {'status': 'full'|'partial', 'paid_amount': ..., 'remaining': ...} yoki None (qarz topilmasa)."""
    debt = await get_debt(debt_id)
    if not debt:
        return None

    current_paid = debt.get("paid_amount") or 0
    new_paid = current_paid + amount
    total = debt["amount"]

    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "INSERT INTO debt_payments (debt_id, amount, paid_at) VALUES (?, ?, ?)",
            (debt_id, amount, _now()),
        )
        if new_paid >= total:
            await db.execute(
                "UPDATE debts SET paid_amount = ?, is_paid = 1 WHERE id = ?",
                (total, debt_id),
            )
            status = "full"
            new_paid = total
        else:
            await db.execute(
                "UPDATE debts SET paid_amount = ? WHERE id = ?",
                (new_paid, debt_id),
            )
            status = "partial"
        await db.commit()

    return {"status": status, "paid_amount": new_paid, "remaining": total - new_paid}


async def get_debt_payments(debt_id: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM debt_payments WHERE debt_id = ? ORDER BY paid_at", (debt_id,)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
