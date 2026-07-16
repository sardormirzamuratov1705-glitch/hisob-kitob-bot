import os
from datetime import datetime

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
                created_at TEXT NOT NULL
            )
            """
        )
        # Eski bazalarda bu ustun bo'lmasligi mumkin - xavfsiz qo'shib qo'yamiz.
        try:
            await db.execute("ALTER TABLE products ADD COLUMN channel_message_id INTEGER")
        except Exception:
            pass
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                amount REAL NOT NULL,
                description TEXT,
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
                created_at TEXT NOT NULL
            )
            """
        )
        await db.commit()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------- MAHSULOTLAR (SKLAD) ----------

async def add_product(name: str, price: float, quantity: float, photo_file_id, channel_message_id=None):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "INSERT INTO products (name, price, quantity, photo_file_id, channel_message_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (name, price, quantity, photo_file_id, channel_message_id, _now()),
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


# ---------- KIRIM / CHIQIM (TRANSAKSIYALAR) ----------

async def add_transaction(type_: str, amount: float, description: str):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "INSERT INTO transactions (type, amount, description, created_at) VALUES (?, ?, ?, ?)",
            (type_, amount, description, _now()),
        )
        await db.commit()


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


# ---------- QARZDORLAR ----------

async def add_debt(customer_name: str, phone: str, amount: float, description: str):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "INSERT INTO debts (customer_name, phone, amount, description, is_paid, created_at) "
            "VALUES (?, ?, ?, ?, 0, ?)",
            (customer_name, phone, amount, description, _now()),
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
            "SELECT COALESCE(SUM(amount), 0) FROM debts WHERE is_paid = 0"
        )
        return (await cursor.fetchone())[0]


async def mark_debt_paid(debt_id: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("UPDATE debts SET is_paid = 1 WHERE id = ?", (debt_id,))
        await db.commit()
