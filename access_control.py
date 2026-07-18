import logging

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery

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
    """Botga umuman kirish huquqi bor-yo'qligini tekshiradi: bosh admin,
    bosh admin tomonidan bazaga do'kon egasi sifatida qo'shilgan foydalanuvchi,
    YOKI biror do'kon egasi tomonidan o'sha do'konga sotuvchi sifatida
    qo'shilgan foydalanuvchi."""
    if is_admin(user_id):
        return True
    if await db.is_owner(user_id):
        return True
    return await db.is_seller(user_id)


async def get_role(user_id: int):
    """Foydalanuvchining rolini qaytaradi: "admin" | "owner" | "seller" | None.

    Tekshirish tartibi muhim: bir kishi ham admin, ham owner/seller bo'la
    olmaydi (add_owner/add_seller bunday holatlarni allaqachon oldini oladi),
    lekin xavfsizlik uchun admin birinchi tekshiriladi."""
    if is_admin(user_id):
        return "admin"
    if await db.is_owner(user_id):
        return "owner"
    if await db.is_seller(user_id):
        return "seller"
    return None


async def is_owner_level(user_id: int) -> bool:
    """True - faqat HAQIQIY do'kon egasi uchun (bosh admin ham, sotuvchi ham
    emas). Narx belgilash, qo'lda miqdor o'zgartirish, kirim/chiqim, hisobot,
    sotuvchi boshqarish kabi "faqat egaga" tegishli amallar shuni ishlatadi."""
    return await db.is_owner(user_id)


async def get_shop_id(user_id: int):
    """Foydalanuvchining do'koni (shop_id):
    - do'kon egasi uchun - har doim o'zining telegram_id'siga teng
      (1 egа = 1 mustaqil do'kon);
    - sotuvchi uchun - u qaysi do'konga biriktirilgan bo'lsa, o'sha do'kon
      egasining telegram_id'si (sellers jadvalidan olinadi);
    - bosh admin uchun - None (uning o'z do'koni yo'q).

    Sklad/Savdo/Qarz/Hisobot bo'limlaridagi har bir handler ishlatishdan oldin
    shop_id None emasligini tekshirishi kerak (u holat faqat bosh admin
    adashib shu bo'limga kirmoqchi bo'lganda yuz beradi - normal holatda
    bunday tugmalar bosh adminga ko'rsatilmaydi).
    """
    if await db.is_owner(user_id):
        return user_id
    seller_shop_id = await db.get_seller_shop_id(user_id)
    if seller_shop_id:
        return seller_shop_id
    return None


async def get_branch_id(user_id: int):
    """Foydalanuvchining joriy filiali (branch_id):
    - do'kon egasi uchun - o'zi tanlab qo'ygan joriy filial
      (owners.current_branch_id). Hali birorta filial tanlamagan bo'lsa -
      None, ya'ni "Bosh filial" (filialga bo'linmagan umumiy holat).
    - sotuvchi uchun - doimiy biriktirilgan filiali (sellers.branch_id).
      Sotuvchi buni o'zi almashtira olmaydi - faqat do'kon egasi
      "📋 Sotuvchilar ro'yxati" orqali boshqa filialga ko'chira oladi.
    - bosh admin uchun - None (uning o'z do'koni/filiali yo'q).

    Savdo/Kirim-Chiqim/Qarz yozuvlarini kiritishdan oldin har bir handler
    shuni chaqirib, yozuvga shu branch_id'ni biriktirishi kerak.
    """
    owner = await db.get_owner(user_id)
    if owner:
        return owner.get("current_branch_id")
    seller = await db.get_seller(user_id)
    if seller:
        return seller.get("branch_id")
    return None


class OwnerOnlyMiddleware(BaseMiddleware):
    """Botning barcha funksiyalari (Sklad, Kirim/Chiqim, Qarz daftar, Hisobot va h.k.)
    faqat bosh admin (config.ADMIN_IDS), bazaga qo'shilgan do'kon egalari va
    ularning sotuvchilariga ochiq.

    Ikkita istisno:
    1) /start buyrug'i - bu mijozlarga qarz eslatmasi uchun yuborilgan
       shaxsiy link (t.me/bot?start=debt_<id>) orqali botni ochish imkonini
       beradi, shuningdek notanish odamga "landing" oynasini ko'rsatadi.
       handlers/start.py o'zi ruxsatsiz holatlarda faqat shu ekranlarni
       beradi va hech qanday maxfiy menyu ko'rsatmaydi - shuning uchun
       /start ni oddiy o'tkazib yuborish xavfsiz.
    2) "self_register" callback tugmasi - landing oynasidagi "Ro'yxatdan
       o'tish" tugmasi notanish odam uchun ham ishlashi kerak.

    Boshqa BARCHA xabar/tugma bosish (matn, callback) begona foydalanuvchidan
    kelsa - hech narsa qilinmasdan e'tiborsiz qoldiriladi.

    DIQQAT: bu middleware faqat botga umuman kirish huquqini tekshiradi.
    Sotuvchining aniq QAYSI bo'limlarga (Sklad narx belgilash, Kirim/Chiqim,
    Hisobot va h.k.) kira olmasligi har bir handler ichida alohida
    tekshiriladi (is_owner_level orqali) - chunki sotuvchi ham "authorized",
    faqat cheklangan huquqlar bilan.
    """

    async def __call__(self, handler, event, data):
        user = event.from_user
        if user and await is_authorized(user.id):
            return await handler(event, data)

        if isinstance(event, Message) and event.text and event.text.startswith("/start"):
            return await handler(event, data)

        # "Landing" oynasidagi "📝 Ro'yxatdan o'tish" tugmasi - hali botga
        # umuman notanish (is_authorized=False) odam ham buni bosa olishi
        # kerak, aks holda tugma jim (hech narsa qilmay) qolib ketadi.
        if isinstance(event, CallbackQuery) and event.data == "self_register":
            return await handler(event, data)

        if user:
            logging.info(f"OwnerOnlyMiddleware: ruxsatsiz urinish - user_id={user.id}")
        return
