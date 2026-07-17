import logging

from aiogram import Router, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

import database as db
import keyboards as kb
from access_control import is_admin, is_authorized, get_role

router = Router()


@router.message(CommandStart(deep_link=True))
async def cmd_start_deep_link(message: Message, state: FSMContext, command: CommandObject):
    """Mijoz "Qarz qo'shish" bo'limida yaratilgan shaxsiy link orqali
    (t.me/bot?start=debt_<id>) botni ochganda, yoki do'kon egasi/sotuvchi
    bir martalik taklif linki orqali botni ochganda ishga tushadi."""
    await state.clear()
    payload = command.args or ""

    if payload.startswith("owner_"):
        token = payload.split("_", 1)[1]
        invite = await db.get_owner_invite(token)

        if not invite:
            await message.answer("❌ Bu link amal qilmaydi (noto'g'ri yoki eskirgan).")
            return
        if invite.get("used_by"):
            await message.answer(
                "❌ Bu link allaqachon ishlatilgan. Har bir taklif linki faqat "
                "BITTA marta, bitta odam uchun amal qiladi. Yangi link so'rang."
            )
            return

        if is_admin(message.from_user.id):
            await message.answer("Siz allaqachon bosh adminsiz - bu link sizga kerak emas.")
            return
        if await db.is_owner(message.from_user.id):
            await message.answer("Siz allaqachon do'kon egasi sifatida ro'yxatdasiz.")
            return
        if await db.is_seller(message.from_user.id):
            await message.answer("Siz allaqachon bir do'konga sotuvchi sifatida ulangansiz.")
            return

        # Race-safe: agar shu vaqtda boshqa birov ham xuddi shu tokenni
        # ishlatmoqchi bo'lsa, faqat biri muvaffaqiyatli bo'ladi.
        claimed = await db.use_owner_invite(token, message.from_user.id)
        if not claimed:
            await message.answer(
                "❌ Bu link boshqa birov tomonidan sizdan bir zum oldin ishlatib bo'lingan."
            )
            return

        await db.add_owner(
            message.from_user.id,
            message.from_user.full_name,
            message.from_user.username,
            added_by=invite["created_by"],
        )
        await message.answer(
            "✅ Tabriklaymiz! Siz do'kon egasi sifatida ro'yxatdan o'tdingiz.\n\n"
            "Quyidagi bo'limlardan birini tanlang:",
            reply_markup=kb.main_menu("owner")
        )
        try:
            await message.bot.send_message(
                invite["created_by"],
                f"✅ Yangi do'kon egasi taklif linki orqali qo'shildi: "
                f"{message.from_user.full_name} (ID: {message.from_user.id})",
            )
        except Exception as e:
            logging.warning(f"Adminga xabar yuborib bo'lmadi: {e}")
        return

    if payload.startswith("seller_"):
        token = payload.split("_", 1)[1]
        invite = await db.get_seller_invite(token)

        if not invite:
            await message.answer("❌ Bu link amal qilmaydi (noto'g'ri yoki eskirgan).")
            return
        if invite.get("used_by"):
            await message.answer(
                "❌ Bu link allaqachon ishlatilgan. Har bir taklif linki faqat "
                "BITTA marta, bitta odam uchun amal qiladi. Yangi link so'rang."
            )
            return

        if is_admin(message.from_user.id):
            await message.answer("Siz bosh adminsiz - bu link sizga kerak emas.")
            return
        if await db.is_owner(message.from_user.id):
            await message.answer("Siz allaqachon do'kon egasisiz - bu link sizga kerak emas.")
            return
        if await db.is_seller(message.from_user.id):
            await message.answer("Siz allaqachon bir do'konga sotuvchi sifatida ulangansiz.")
            return

        claimed = await db.use_seller_invite(token, message.from_user.id)
        if not claimed:
            await message.answer(
                "❌ Bu link boshqa birov tomonidan sizdan bir zum oldin ishlatib bo'lingan."
            )
            return

        await db.add_seller(
            message.from_user.id,
            invite["shop_id"],
            message.from_user.full_name,
            message.from_user.username,
            added_by=invite["created_by"],
        )
        await message.answer(
            "✅ Tabriklaymiz! Siz sotuvchi sifatida ro'yxatdan o'tdingiz.\n\n"
            "Quyidagi bo'limlardan birini tanlang:",
            reply_markup=kb.main_menu("seller")
        )
        try:
            await message.bot.send_message(
                invite["created_by"],
                f"✅ Yangi sotuvchi taklif linki orqali qo'shildi: "
                f"{message.from_user.full_name} (ID: {message.from_user.id})",
            )
        except Exception as e:
            logging.warning(f"Do'kon egasiga xabar yuborib bo'lmadi: {e}")
        return

    if payload.startswith("debt_"):
        try:
            debt_id = int(payload.split("_", 1)[1])
        except ValueError:
            debt_id = None

        # Diqqat: bu yerda hali shop_id noma'lum (mijoz hech qanday do'konga
        # a'zo emas), shuning uchun shop_id talab qilmaydigan get_debt_by_id
        # ishlatiladi.
        debt = await db.get_debt_by_id(debt_id) if debt_id else None
        if debt:
            await db.link_debt_customer(
                debt_id,
                message.from_user.id,
                message.from_user.username,
            )
            await message.answer(
                "✅ Xush kelibsiz! Endi qarzdorlik va to'lovlar haqida eslatmalarni "
                "shu bot orqali olasiz."
            )

            # MUHIM: faqat shu qarz tegishli bo'lgan DO'KON EGASIGA xabar beramiz,
            # boshqa do'kon egalariga yoki bosh adminga emas - aks holda boshqa
            # do'konlar bu mijoz va uning qarzi haqida bilib qolar edi.
            shop_owner_id = debt.get("shop_id")
            if shop_owner_id:
                try:
                    await message.bot.send_message(
                        shop_owner_id,
                        f"🔗 <b>{debt['customer_name']}</b> shaxsiy link orqali botga ulandi.\n"
                        f"Endi unga to'g'ridan-to'g'ri eslatma yuborish mumkin.",
                        parse_mode="HTML",
                    )
                except Exception as e:
                    logging.warning(f"Do'kon egasiga xabar yuborib bo'lmadi ({shop_owner_id}): {e}")
            return

    # Noto'g'ri yoki eskirgan link bo'lsa, oddiy /start kabi davom etamiz.
    role = await get_role(message.from_user.id)
    if role is None:
        await message.answer(
            "Assalomu alaykum! Bu link amal qilmaydi yoki muddati o'tgan."
        )
        return
    await message.answer(
        "Assalomu alaykum! Do'kon boshqaruv botiga xush kelibsiz.\n\n"
        "Quyidagi bo'limlardan birini tanlang:",
        reply_markup=kb.main_menu(role)
    )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    role = await get_role(message.from_user.id)
    if role is None:
        await message.answer(
            "Assalomu alaykum! Bu bot faqat do'kon egasi/xodimlari uchun mo'ljallangan."
        )
        return
    await message.answer(
        "Assalomu alaykum! Do'kon boshqaruv botiga xush kelibsiz.\n\n"
        "Quyidagi bo'limlardan birini tanlang:",
        reply_markup=kb.main_menu(role)
    )


@router.message(F.text == "⬅️ Orqaga")
async def go_back(message: Message, state: FSMContext):
    await state.clear()
    role = await get_role(message.from_user.id)
    if role is None:
        return
    await message.answer("Asosiy menyu:", reply_markup=kb.main_menu(role))


# Quyidagi bo'limlar (Sklad, Kirim/Chiqim, Hisobot, Sotuvchilar) faqat
# HAQIQIY do'kon egalariga tegishli - na bosh adminda, na sotuvchida bunga
# ruxsat yo'q. kb.main_menu() bu tugmalarni ularga umuman ko'rsatmaydi,
# lekin himoyani ikki marta ta'minlash uchun (masalan eski chatdan matnni
# qayta yuborsa) har bir handlerda ham qayta tekshiramiz.

async def _require_owner_only(message: Message) -> bool:
    if not await db.is_owner(message.from_user.id):
        await message.answer("Bu bo'lim faqat do'kon egasi uchun.")
        return False
    return True


# "📒 Qarz daftar" esa do'kon egasi VA sotuvchi uchun ham ochiq (faqat bosh
# admin kira olmaydi) - qarz qo'shish/to'lov qabul qilish sotuvchining
# kundalik ishi.

async def _require_shop_access(message: Message) -> bool:
    if is_admin(message.from_user.id):
        await message.answer("Bu bo'lim faqat do'kon egalari uchun.")
        return False
    return True


@router.message(F.text == "📦 Sklad")
async def open_sklad(message: Message, state: FSMContext):
    await state.clear()
    if not await _require_owner_only(message):
        return
    await message.answer("Sklad bo'limi:", reply_markup=kb.sklad_menu())


@router.message(F.text == "💰 Kirim/Chiqim")
async def open_kirim_chiqim(message: Message, state: FSMContext):
    await state.clear()
    if not await _require_owner_only(message):
        return
    await message.answer("Kirim/Chiqim bo'limi:", reply_markup=kb.kirim_chiqim_menu())


@router.message(F.text == "📒 Qarz daftar")
async def open_qarz(message: Message, state: FSMContext):
    await state.clear()
    if not await _require_shop_access(message):
        return
    await message.answer("Qarz daftar bo'limi:", reply_markup=kb.qarz_menu())


@router.message(F.text == "📊 Hisobot")
async def open_hisobot(message: Message, state: FSMContext):
    await state.clear()
    if not await _require_owner_only(message):
        return
    await message.answer("Hisobot bo'limi:", reply_markup=kb.hisobot_menu())


# ---------- BOSH ADMIN: ZAXIRA NUSXA ----------
# Butun bazani (BARCHA do'konlar) qamrab oladigan texnik zaxira - shuning
# uchun faqat bosh adminga ochiq (handlers/reports.py'dagi export_db/
# restore_db_start ham o'z ichida is_admin() bilan qayta tekshiradi).

@router.message(F.text == "🗄 Zaxira nusxa")
async def open_backup(message: Message, state: FSMContext):
    await state.clear()
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        "🗄 Zaxira nusxa bo'limi (barcha do'konlar):",
        reply_markup=kb.admin_backup_menu(),
    )
