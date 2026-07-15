import aiosqlite
from datetime import datetime
from config import DB_PATH


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                quantity REAL NOT NULL DEFAULT 0,
                photo_file_id TEXT,
                created_at TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,               -- 'income' yoki 'expense'
                amount REAL NOT NULL,
                description TEXT,
                product_id INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY (product_id) REFERENCES products (id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS debts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_name TEXT NOT NULL,
                phone TEXT,
                amount REAL NOT NULL,
                description TEXT,
                is_paid INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                paid_at TEXT
            )
        """)
        await db.commit()


# ---------- PRODUCTS ----------

async def add_product(name: str, price: float, quantity: float, photo_file_id: str | None):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO products (name, price, quantity, photo_file_id, created_at) VALUES (?, ?, ?, ?, ?)",
            (name, price, quantity, photo_file_id, datetime.now().isoformat())
        )
        await db.commit()
        return cur.lastrowid


async def get_all_products():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM products ORDER BY created_at DESC")
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def get_product(product_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def update_product_quantity(product_id: int, delta: float):
    """delta musbat bo'lsa kirim (qo'shiladi), manfiy bo'lsa chiqim (ayiriladi)"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE products SET quantity = quantity + ? WHERE id = ?",
            (delta, product_id)
        )
        await db.commit()


async def delete_product(product_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM products WHERE id = ?", (product_id,))
        await db.commit()


# ---------- TRANSACTIONS ----------

async def add_transaction(type_: str, amount: float, description: str, product_id: int | None = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO transactions (type, amount, description, product_id, created_at) VALUES (?, ?, ?, ?, ?)",
            (type_, amount, description, product_id, datetime.now().isoformat())
        )
        await db.commit()


async def get_transactions(limit: int = 50):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM transactions ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def get_totals():
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE type='income'")
        income = (await cur.fetchone())[0]
        cur = await db.execute("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE type='expense'")
        expense = (await cur.fetchone())[0]
        return income, expense


# ---------- DEBTS ----------

async def add_debt(customer_name: str, phone: str, amount: float, description: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO debts (customer_name, phone, amount, description, is_paid, created_at) "
            "VALUES (?, ?, ?, ?, 0, ?)",
            (customer_name, phone, amount, description, datetime.now().isoformat())
        )
        await db.commit()


async def get_debts(only_unpaid: bool = True):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM debts"
        if only_unpaid:
            query += " WHERE is_paid = 0"
        query += " ORDER BY created_at DESC"
        cur = await db.execute(query)
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def mark_debt_paid(debt_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE debts SET is_paid = 1, paid_at = ? WHERE id = ?",
            (datetime.now().isoformat(), debt_id)
        )
        await db.commit()


async def get_total_debt():
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT COALESCE(SUM(amount),0) FROM debts WHERE is_paid = 0")
        return (await cur.fetchone())[0]
