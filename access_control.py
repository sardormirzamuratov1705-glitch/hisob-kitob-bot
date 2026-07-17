import logging

from aiogram import BaseMiddleware
from aiogram.types import Message

import config
import database as db


def is_admin(user_id: int) -> bool:
    """Bosh admin - faqat .env dagi config.ADMIN_IDS ro'yxatidagilar.
    Faqat shular yangi do'kon egalarini bazaga qo'sha/o'chira oladi
    ("Foydalanuvchilar" bo'limi faqat shularga ko'rinadi)."""
    return user_id in config.ADMIN_IDS


async def is_authorized(user_id: int) -> bool:
    """Botning ish bo'limlariga (Sklad, Kirim/Chiqim, Qarz daftar, Hisobot) kirish
    huquqi bor-yo'qligini tekshiradi: bosh admin YOKI bosh admin tomonidan
    bazaga do'kon egasi sifatida qo'shilgan foydalanuvchi."""
    if is_admin(user_id):
        return True
    return await db.is_owner(user_id)


class OwnerOnlyMiddleware(BaseMiddleware):
    """Botning barcha funksiyalari (Sklad, Kirim/Chiqim, Qarz daftar, Hisobot va h.k.)
    faqat bosh admin (config.ADMIN_IDS) va bazaga qo'shilgan do'kon egalariga ochiq.

    Yagona istisno: /start buyrug'i - bu mijozlarga qarz eslatmasi uchun
    yuborilgan shaxsiy link (t.me/bot?start=debt_<id>) orqali botni ochish
    imkonini beradi. handlers/start.py o'zi bu holatda faqat "botga ulandi"
    xabarini beradi va hech qanday menyu ko'rsatmaydi - shuning uchun bu yerda
    /start ni oddiy o'tkazib yuborish xavfsiz.

    Boshqa BARCHA xabar/tugma bosish (matn, callback) begona foydalanuvchidan
    kelsa - hech narsa qilinmasdan e'tiborsiz qoldiriladi."""

    async def __call__(self, handler, event, data):
        user = event.from_user
        if user and await is_authorized(user.id):
            return await handler(event, data)

        if isinstance(event, Message) and event.text and event.text.startswith("/start"):
            return await handler(event, data)

        if user:
            logging.info(f"OwnerOnlyMiddleware: ruxsatsiz urinish - user_id={user.id}")
        return
