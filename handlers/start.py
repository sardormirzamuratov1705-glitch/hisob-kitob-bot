import logging

from aiogram import Router, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

import config
import database as db
import keyboards as kb

router = Router()


def _is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


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

        debt = await db.get_debt(debt_id) if debt_id else None
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

            for admin_id in config.ADMIN_IDS:
                try:
                    await message.bot.send_message(
                        admin_id,
                        f"🔗 <b>{debt['customer_name']}</b> shaxsiy link orqali botga ulandi.\n"
                        f"Endi unga to'g'ridan-to'g'ri eslatma yuborish mumkin.",
                        parse_mode="HTML",
                    )
                except Exception as e:
                    logging.warning(f"Admin'ga xabar yuborib bo'lmadi ({admin_id}): {e}")
            return

    # Noto'g'ri yoki eskirgan link bo'lsa, oddiy /start kabi davom etamiz.
    if not _is_admin(message.from_user.id):
        await message.answer(
            "Assalomu alaykum! Bu link amal qilmaydi yoki muddati o'tgan."
        )
        return
    await message.answer(
        "Assalomu alaykum! Do'kon boshqaruv botiga xush kelibsiz.\n\n"
        "Quyidagi bo'limlardan birini tanlang:",
        reply_markup=kb.main_menu()
    )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    if not _is_admin(message.from_user.id):
        await message.answer(
            "Assalomu alaykum! Bu bot faqat do'kon egasi/xodimlari uchun mo'ljallangan."
        )
        return
    await message.answer(
        "Assalomu alaykum! Do'kon boshqaruv botiga xush kelibsiz.\n\n"
        "Quyidagi bo'limlardan birini tanlang:",
        reply_markup=kb.main_menu()
    )


@router.message(F.text == "⬅️ Orqaga")
async def go_back(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Asosiy menyu:", reply_markup=kb.main_menu())


@router.message(F.text == "📦 Sklad")
async def open_sklad(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Sklad bo'limi:", reply_markup=kb.sklad_menu())


@router.message(F.text == "💰 Kirim/Chiqim")
async def open_kirim_chiqim(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Kirim/Chiqim bo'limi:", reply_markup=kb.kirim_chiqim_menu())


@router.message(F.text == "📒 Qarz daftar")
async def open_qarz(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Qarz daftar bo'limi:", reply_markup=kb.qarz_menu())


@router.message(F.text == "📊 Hisobot")
async def open_hisobot(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Hisobot bo'limi:", reply_markup=kb.hisobot_menu())
