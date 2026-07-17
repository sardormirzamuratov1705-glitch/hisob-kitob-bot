import logging

from aiogram import BaseMiddleware
from aiogram.types import Message

import config
import database as db


def is_admin(user_id: int) -> bool:
    """Bosh admin - faqat .env dagi config.ADMIN_IDS ro'yxatidagilar.
    Faqat shular yangi do'kon egalarini bazaga qo'sha/o'chira oladi
    ("Foydalanuvchilar" bo'limi faqat shularga ko'rinadi). Bosh adminning
    o'zining alohida do'koni (Sklad/Savdo/Qarz/Hisobot) yo'q - u faqat
    do'kon egalarini boshqaradi."""
    return user_id in config.ADMIN_IDS


async def is_authorized(user_id: int) -> bool:
    """Botga umuman kirish huquqi bor-yo'qligini tekshiradi: bosh admin YOKI
    bosh admin tomonidan bazaga do'kon egasi sifatida qo'shilgan foydalanuvchi."""
    if is_admin(user_id):
        return True
    return await db.is_owner(user_id)


async def get_shop_id(user_id: int):
    """Foydalanuvchining do'koni (shop_id) - do'kon egasi uchun har doim
    o'zining telegram_id'siga teng (1 egа = 1 mustaqil do'kon).

    Bosh adminning o'z do'koni yo'q - shuning uchun bosh admin uchun None
    qaytariladi. Sklad/Savdo/Qarz/Hisobot bo'limlaridagi har bir handler
    ishlatishdan oldin shop_id None emasligini tekshirishi kerak (u holat
    faqat bosh admin adashib shu bo'limga kirmoqchi bo'lganda yuz beradi -
    normal holatda bunday tugmalar bosh adminga ko'rsatilmaydi)."""
    if await db.is_owner(user_id):
        return user_id
    return None


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
