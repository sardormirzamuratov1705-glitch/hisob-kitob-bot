from datetime import datetime

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

import database as db
import keyboards as kb
import alerts

router = Router()


async def _debt_link(bot, debt_id: int) -> str:
    me = await bot.get_me()
    return f"https://t.me/{me.username}?start=debt_{debt_id}"


class AddDebt(StatesGroup):
    customer_name = State()
    phone = State()
    amount = State()
    description = State()


@router.message(F.text == "➕ Qarz qo'shish")
async def add_debt_start(message: Message, state: FSMContext):
    await state.set_state(AddDebt.customer_name)
    await message.answer("Mijoz ismini kiriting:")


@router.message(AddDebt.customer_name)
async def add_debt_name(message: Message, state: FSMContext):
    await state.update_data(customer_name=message.text.strip())
    await state.set_state(AddDebt.phone)
    await message.answer("Telefon raqamini kiriting (yoki '-' deb yozing):")


@router.message(AddDebt.phone)
async def add_debt_phone(message: Message, state: FSMContext):
    await state.update_data(phone=message.text.strip())
    await state.set_state(AddDebt.amount)
    await message.answer("Qarz summasini kiriting (so'mda):")


@router.message(AddDebt.amount)
async def add_debt_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", ".").replace(" ", ""))
    except ValueError:
        await message.answer("Iltimos, faqat raqam kiriting. Masalan: 500000")
        return
    await state.update_data(amount=amount)
    await state.set_state(AddDebt.description)
    await message.answer("Izoh kiriting (masalan: 'Oziq-ovqat qarzi'):")


@router.message(AddDebt.description)
async def add_debt_description(message: Message, state: FSMContext):
    data = await state.get_data()
    debt_id = await db.add_debt(data["customer_name"], data["phone"], data["amount"], message.text.strip())
    await state.clear()

    link = await _debt_link(message.bot, debt_id)
    await message.answer(
        f"✅ Qarz qo'shildi:\n"
        f"Mijoz: {data['customer_name']}\n"
        f"Summasi: {data['amount']:.0f} so'm",
        reply_markup=kb.qarz_menu()
    )
    await message.answer(
        "🔗 Bu mijozga eslatmalarni bevosita botdan yuborish uchun, "
        "quyidagi shaxsiy linkni unga yuboring (Telegram, WhatsApp — qayerda bo'lsa ham). "
        "U shu linkni bosib botni ochsa, keyin unga to'g'ridan-to'g'ri eslatma yuborib turamiz:\n\n"
        f"{link}"
    )


@router.message(F.text == "📋 Qarzdorlar ro'yxati")
async def list_debts(message: Message):
    debts = await db.get_debts(only_unpaid=True)
    if not debts:
        await message.answer("Qarzdorlar yo'q. 🎉")
        return

    total = await db.get_total_debt()
    await message.answer(f"Umumiy qarzdorlik: <b>{total:.0f} so'm</b>", parse_mode="HTML")

    for d in debts:
        try:
            created_dt = datetime.strptime(d["created_at"], "%Y-%m-%d %H:%M:%S")
            days_ago = (datetime.now() - created_dt).days
        except (TypeError, ValueError):
            days_ago = None

        age_line = ""
        if days_ago is not None:
            if days_ago >= 3:
                age_line = f"⏰ {days_ago} kundan beri qarzda\n"
            else:
                age_line = f"🕐 {days_ago} kun oldin\n"

        linked = bool(d.get("customer_chat_id"))
        link_line = "\n🔗 Botga ulangan (eslatma yuborish mumkin)" if linked else ""
        text = (
            f"👤 <b>{d['customer_name']}</b>\n"
            f"📞 {d['phone']}\n"
            f"💵 {d['amount']:.0f} so'm\n"
            f"{age_line}"
            f"📝 {d['description']}"
            f"{link_line}"
        )
        await message.answer(
            text,
            reply_markup=kb.debt_action_kb(d["id"], customer_linked=linked),
            parse_mode="HTML"
        )


@router.callback_query(F.data.startswith("pay_debt_"))
async def mark_paid_cb(callback: CallbackQuery):
    debt_id = int(callback.data.split("_")[-1])
    await db.mark_debt_paid(debt_id)
    await callback.answer("Qarz to'landi deb belgilandi ✅")
    try:
        await callback.message.edit_text(callback.message.text + "\n\n✅ TO'LANDI")
    except Exception:
        pass


@router.callback_query(F.data.startswith("remind_debt_"))
async def remind_debt_cb(callback: CallbackQuery):
    debt_id = int(callback.data.split("_")[-1])
    debt = await db.get_debt(debt_id)
    if not debt:
        await callback.answer("Qarz topilmadi", show_alert=True)
        return

    sent = await alerts.send_customer_debt_reminder(callback.bot, debt)
    if sent:
        await callback.answer("✅ Eslatma mijozga yuborildi", show_alert=True)
    else:
        await callback.answer("❌ Mijoz hali botga ulanmagan", show_alert=True)


@router.callback_query(F.data.startswith("debt_link_"))
async def debt_link_cb(callback: CallbackQuery):
    debt_id = int(callback.data.split("_")[-1])
    debt = await db.get_debt(debt_id)
    if not debt:
        await callback.answer("Qarz topilmadi", show_alert=True)
        return

    link = await _debt_link(callback.bot, debt_id)
    await callback.answer()
    await callback.message.answer(
        f"🔗 <b>{debt['customer_name']}</b> uchun shaxsiy link:\n{link}\n\n"
        "Buni mijozga yuboring — u linkni bosib botni ochsa, "
        "keyin unga to'g'ridan-to'g'ri eslatma yuborish mumkin bo'ladi.",
        parse_mode="HTML",
    )
