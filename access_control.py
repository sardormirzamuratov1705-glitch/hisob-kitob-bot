import logging

from aiogram import BaseMiddleware
from aiogram.types import Message

import config


class OwnerOnlyMiddleware(BaseMiddleware):
    """Botning barcha funksiyalari (Sklad, Kirim/Chiqim, Qarz daftar, Hisobot va h.k.)
    faqat config.ADMIN_IDS ro'yxatidagi foydalanuvchilarga ochiq.

    Yagona istisno: /start buyrug'i - bu mijozlarga qarz eslatmasi uchun
    yuborilgan shaxsiy link (t.me/bot?start=debt_<id>) orqali botni ochish
    imkonini beradi. handlers/start.py o'zi bu holatda faqat "botga ulandi"
    xabarini beradi va hech qanday menyu ko'rsatmaydi - shuning uchun bu yerda
    /start ni oddiy o'tkazib yuborish xavfsiz.

    Boshqa BARCHA xabar/tugma bosish (matn, callback) begona foydalanuvchidan
    kelsa - hech narsa qilinmasdan e'tiborsiz qoldiriladi."""

    async def __call__(self, handler, event, data):
        user = event.from_user
        if user and user.id in config.ADMIN_IDS:
            return await handler(event, data)

        if isinstance(event, Message) and event.text and event.text.startswith("/start"):
            return await handler(event, data)

        if user:
            logging.info(f"OwnerOnlyMiddleware: ruxsatsiz urinish - user_id={user.id}")
        return
