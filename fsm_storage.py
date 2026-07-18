"""3-BOSQICH: FSM holatini (kim, qaysi formani, qaysi bosqichda to'ldirib
turgani) RAM'da emas, bazada (config.DB_PATH, fsm_storage jadvali) saqlaydi.

Muammo: aiogram'ning standart MemoryStorage'i holatni faqat RAM'da saqlaydi -
bot redeploy qilinganda (yoki qulab, qayta ishga tushganda) o'sha payt biror
forma to'ldirib turgan (masalan mahsulot qo'shayotgan, savdo qilayotgan)
foydalanuvchining holati butunlay yo'qolib, u boshidan boshlashga majbur
bo'lardi.

Yechim: shu klass - aiogram.fsm.storage.base.BaseStorage'ning bazaga
yozib boradigan, minimal implementatsiyasi. Yangi server/xizmat (masalan
Redis) shart emas - Volume'da allaqachon mavjud bo'lgan shop.db faylining
o'zidan foydalanadi, shuning uchun qo'shimcha sozlash kerak emas.
"""

import json

import aiosqlite
from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StorageKey

import config


def _now() -> str:
    from datetime import datetime
    return config.now().strftime("%Y-%m-%d %H:%M:%S")


class SQLiteStorage(BaseStorage):
    """StorageKey'dagi thread_id/business_connection_id maydonlari odatda
    None bo'ladi (bu bot guruh mavzulari yoki biznes hisoblari bilan
    ishlamaydi) - lekin SQLite'da PRIMARY KEY ustunidagi NULL qiymatlar
    "ON CONFLICT" uchun bir-biriga teng hisoblanmaydi (har safar NULL o'zgacha
    deb hisoblanadi), shuning uchun ular saqlashda 0 / '' ga almashtiriladi."""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or config.DB_PATH

    @staticmethod
    def _key_tuple(key: StorageKey):
        return (
            key.bot_id,
            key.chat_id,
            key.user_id,
            key.thread_id or 0,
            key.business_connection_id or "",
            key.destiny,
        )

    async def set_state(self, key: StorageKey, state=None) -> None:
        if isinstance(state, State):
            state = state.state

        bot_id, chat_id, user_id, thread_id, bc_id, destiny = self._key_tuple(key)
        async with aiosqlite.connect(self.db_path, timeout=10) as db:
            await db.execute(
                """
                INSERT INTO fsm_storage
                    (bot_id, chat_id, user_id, thread_id, business_connection_id,
                     destiny, state, data, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, '{}', ?)
                ON CONFLICT(bot_id, chat_id, user_id, thread_id, business_connection_id, destiny)
                DO UPDATE SET state = excluded.state, updated_at = excluded.updated_at
                """,
                (bot_id, chat_id, user_id, thread_id, bc_id, destiny, state, _now()),
            )
            await db.commit()

    async def get_state(self, key: StorageKey):
        bot_id, chat_id, user_id, thread_id, bc_id, destiny = self._key_tuple(key)
        async with aiosqlite.connect(self.db_path, timeout=10) as db:
            cursor = await db.execute(
                "SELECT state FROM fsm_storage WHERE bot_id = ? AND chat_id = ? AND user_id = ? "
                "AND thread_id = ? AND business_connection_id = ? AND destiny = ?",
                (bot_id, chat_id, user_id, thread_id, bc_id, destiny),
            )
            row = await cursor.fetchone()
            return row[0] if row else None

    async def set_data(self, key: StorageKey, data: dict) -> None:
        bot_id, chat_id, user_id, thread_id, bc_id, destiny = self._key_tuple(key)
        payload = json.dumps(data, ensure_ascii=False)
        async with aiosqlite.connect(self.db_path, timeout=10) as db:
            await db.execute(
                """
                INSERT INTO fsm_storage
                    (bot_id, chat_id, user_id, thread_id, business_connection_id,
                     destiny, state, data, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?)
                ON CONFLICT(bot_id, chat_id, user_id, thread_id, business_connection_id, destiny)
                DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at
                """,
                (bot_id, chat_id, user_id, thread_id, bc_id, destiny, payload, _now()),
            )
            await db.commit()

    async def get_data(self, key: StorageKey) -> dict:
        bot_id, chat_id, user_id, thread_id, bc_id, destiny = self._key_tuple(key)
        async with aiosqlite.connect(self.db_path, timeout=10) as db:
            cursor = await db.execute(
                "SELECT data FROM fsm_storage WHERE bot_id = ? AND chat_id = ? AND user_id = ? "
                "AND thread_id = ? AND business_connection_id = ? AND destiny = ?",
                (bot_id, chat_id, user_id, thread_id, bc_id, destiny),
            )
            row = await cursor.fetchone()
            if not row or not row[0]:
                return {}
            try:
                return json.loads(row[0])
            except (TypeError, ValueError):
                return {}

    async def close(self) -> None:
        # Har bir amal o'z ulanishini ochib-yopadi (database.py'dagi kabi),
        # shuning uchun yopadigan doimiy ulanish yo'q.
        pass
