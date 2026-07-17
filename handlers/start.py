import logging

from aiogram import Router, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

import database as db
import keyboards as kb
from access_control import is_admin, is_authorized

router = Router()


@router.message(CommandStart(deep_link=True))
async def cmd_start_deep_link(message: Message, state: FSMContext, command: CommandObject):
    """Mijoz \"Qarz qo'shish\" bo'limida yaratilgan shaxsiy link orqali
    (t.me/bot?start=debt_<id>) botni ochganda ishga tushadi. Mijozning
    Telegram chat_id/username'ini shu qarz yozuviga bog'laydi, shundan
    keyin bot unga to'g'ridan-to'g'ri eslatma yubora oladi."""
    await state.clear()
    payload = command.args or ""

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
    if not await is_authorized(message.from_user.id):
        await message.answer(
            "Assalomu alaykum! Bu link amal qilmaydi yoki muddati o'tgan."
        )
        return
    await message.answer(
        "Assalomu alaykum! Do'kon boshqaruv botiga xush kelibsiz.\n\n"
        "Quyidagi bo'limlardan birini tanlang:",
        reply_markup=kb.main_menu(is_admin(message.from_user.id))
    )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    if not await is_authorized(message.from_user.id):
        await message.answer(
            "Assalomu alaykum! Bu bot faqat do'kon egasi/xodimlari uchun mo'ljallangan."
        )
        return
    await message.answer(
        "Assalomu alaykum! Do'kon boshqaruv botiga xush kelibsiz.\n\n"
        "Quyidagi bo'limlardan birini tanlang:",
        reply_markup=kb.main_menu(is_admin(message.from_user.id))
    )


@router.message(F.text == "⬅️ Orqaga")
async def go_back(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Asosiy menyu:", reply_markup=kb.main_menu(is_admin(message.from_user.id)))


# Quyidagi 4 ta bo'lim (Sklad, Kirim/Chiqim, Qarz daftar, Hisobot) faqat
# do'kon egalariga tegishli - bosh adminning o'z do'koni yo'q. kb.main_menu()
# bosh adminga bu tugmalarni umuman ko'rsatmaydi, lekin himoyani ikki marta
# ta'minlash uchun (masalan eski chatdan matnni qayta yuborsa) har bir
# handlerda ham qayta tekshiramiz.

async def _require_owner(message: Message) -> bool:
    if is_admin(message.from_user.id):
        await message.answer("Bu bo'lim faqat do'kon egalari uchun.")
        return False
    return True


@router.message(F.text == "📦 Sklad")
async def open_sklad(message: Message, state: FSMContext):
    await state.clear()
    if not await _require_owner(message):
        return
    await message.answer("Sklad bo'limi:", reply_markup=kb.sklad_menu())


@router.message(F.text == "💰 Kirim/Chiqim")
async def open_kirim_chiqim(message: Message, state: FSMContext):
    await state.clear()
    if not await _require_owner(message):
        return
    await message.answer("Kirim/Chiqim bo'limi:", reply_markup=kb.kirim_chiqim_menu())


@router.message(F.text == "📒 Qarz daftar")
async def open_qarz(message: Message, state: FSMContext):
    await state.clear()
    if not await _require_owner(message):
        return
    await message.answer("Qarz daftar bo'limi:", reply_markup=kb.qarz_menu())


@router.message(F.text == "📊 Hisobot")
async def open_hisobot(message: Message, state: FSMContext):
    await state.clear()
    if not await _require_owner(message):
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
