import aiosqlite

import config


async def init_db():
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                quantity REAL NOT NULL,
                photo_file_id TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                amount REAL NOT NULL,
                description TEXT,
                created_at TEXT DEFAULT (datetime('now'))
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
                is_paid INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        await db.commit()


# ---------- MAHSULOTLAR ----------

async def add_product(name, price, quantity, photo_file_id):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "INSERT INTO products (name, price, quantity, photo_file_id) VALUES (?, ?, ?, ?)",
            (name, price, quantity, photo_file_id),
        )
        await db.commit()


async def get_all_products():
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM products ORDER BY id DESC")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def delete_product(product_id):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("DELETE FROM products WHERE id = ?", (product_id,))
        await db.commit()


# ---------- KIRIM/CHIQIM ----------

async def add_transaction(type_, amount, description):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "INSERT INTO transactions (type, amount, description) VALUES (?, ?, ?)",
            (type_, amount, description),
        )
        await db.commit()


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


async def get_transactions(limit=1000):
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM transactions ORDER BY id DESC LIMIT ?", (limit,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


# ---------- QARZ DAFTAR ----------

async def add_debt(customer_name, phone, amount, description):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "INSERT INTO debts (customer_name, phone, amount, description) VALUES (?, ?, ?, ?)",
            (customer_name, phone, amount, description),
        )
        await db.commit()


async def get_debts(only_unpaid=True):
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if only_unpaid:
            cursor = await db.execute("SELECT * FROM debts WHERE is_paid = 0 ORDER BY id DESC")
        else:
            cursor = await db.execute("SELECT * FROM debts ORDER BY id DESC")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_total_debt():
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM debts WHERE is_paid = 0"
        )
        return (await cursor.fetchone())[0]


async def mark_debt_paid(debt_id):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("UPDATE debts SET is_paid = 1 WHERE id = ?", (debt_id,))
        await db.commit()
