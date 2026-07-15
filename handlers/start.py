from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

import keyboards as kb

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
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
