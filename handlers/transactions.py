from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

import database as db
import keyboards as kb

router = Router()


class AddTransaction(StatesGroup):
    amount = State()
    description = State()


# ---------- KIRIM ----------

@router.message(F.text == "➕ Kirim qo'shish")
async def add_income_start(message: Message, state: FSMContext):
    await state.update_data(type="income")
    await state.set_state(AddTransaction.amount)
    await message.answer("Kirim summasini kiriting (so'mda):")


# ---------- CHIQIM ----------

@router.message(F.text == "➖ Chiqim qo'shish")
async def add_expense_start(message: Message, state: FSMContext):
    await state.update_data(type="expense")
    await state.set_state(AddTransaction.amount)
    await message.answer("Chiqim summasini kiriting (so'mda):")


@router.message(AddTransaction.amount)
async def add_transaction_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", ".").replace(" ", ""))
    except ValueError:
        await message.answer("Iltimos, faqat raqam kiriting. Masalan: 150000")
        return
    await state.update_data(amount=amount)
    await state.set_state(AddTransaction.description)
    await message.answer("Izoh kiriting (masalan: 'Un sotib olindi' yoki 'Kunlik savdo'):")


@router.message(AddTransaction.description)
async def add_transaction_description(message: Message, state: FSMContext):
    data = await state.get_data()
    await db.add_transaction(data["type"], data["amount"], message.text.strip())
    await state.clear()

    label = "Kirim" if data["type"] == "income" else "Chiqim"
    await message.answer(
        f"✅ {label} qo'shildi: {data['amount']:.0f} so'm\nIzoh: {message.text.strip()}",
        reply_markup=kb.kirim_chiqim_menu()
    )


# ---------- BUGUNGI HOLAT ----------

@router.message(F.text == "📈 Bugungi holat")
async def today_status(message: Message):
    income, expense = await db.get_totals()
    balance = income - expense
    await message.answer(
        f"📈 <b>Umumiy holat</b>\n\n"
        f"Kirim: {income:.0f} so'm\n"
        f"Chiqim: {expense:.0f} so'm\n"
        f"Balans: <b>{balance:.0f} so'm</b>",
        parse_mode="HTML"
    )
