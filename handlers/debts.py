from datetime import datetime, timedelta

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
    taken_date = State()
    due_date = State()
    description = State()


class PayDebt(StatesGroup):
    amount = State()


def _parse_taken_date(text: str) -> str:
    """'kun.oy.yil' formatidagi matnni 'YYYY-MM-DD' ko'rinishiga o'tkazadi.
    Noto'g'ri format uchun ValueError ko'taradi."""
    dt = datetime.strptime(text.strip(), "%d.%m.%Y")
    return dt.strftime("%Y-%m-%d")


def _parse_due_date(text: str):
    """Foydalanuvchi kiritgan matnni qaytarish sanasiga aylantiradi.

    Qo'llab-quvvatlanadi:
    - "-" - sanasiz (None qaytaradi)
    - butun son (masalan "7") - bugundan shuncha kun keyin
    - "kun.oy.yil" (masalan "25.07.2026") - aniq sana

    Noto'g'ri format uchun ValueError ko'taradi.
    """
    text = text.strip()
    if text == "-":
        return None
    if text.isdigit():
        due = datetime.now() + timedelta(days=int(text))
        return due.strftime("%Y-%m-%d")
    due = datetime.strptime(text, "%d.%m.%Y")
    return due.strftime("%Y-%m-%d")


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
    await state.set_state(AddDebt.taken_date)
    await message.answer(
        "Qarzni qachon oldi?",
        reply_markup=kb.taken_date_kb()
    )


@router.callback_query(AddDebt.taken_date, F.data == "taken_today")
async def add_debt_taken_today(callback: CallbackQuery, state: FSMContext):
    await state.update_data(taken_date=datetime.now().strftime("%Y-%m-%d"))
    await state.set_state(AddDebt.due_date)
    await callback.answer()
    await callback.message.answer(
        "Qarzni qaytarish sanasini kiriting:\n"
        "— aniq sana: kun.oy.yil, masalan 25.07.2026\n"
        "— yoki necha kundan keyin: masalan 7\n"
        "— yoki sanasiz davom etish uchun '-' deb yozing",
        reply_markup=kb.skip_due_date_kb()
    )


@router.callback_query(AddDebt.taken_date, F.data == "taken_custom")
async def add_debt_taken_custom_prompt(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer("Qarz olingan sanani kiriting: kun.oy.yil (masalan 10.07.2026):")


@router.message(AddDebt.taken_date)
async def add_debt_taken_date_text(message: Message, state: FSMContext):
    try:
        taken_date = _parse_taken_date(message.text)
    except ValueError:
        await message.answer(
            "Iltimos, sanani to'g'ri formatda kiriting: kun.oy.yil (masalan 10.07.2026), "
            "yoki yuqoridagi 'Bugun' tugmasini bosing."
        )
        return
    await state.update_data(taken_date=taken_date)
    await state.set_state(AddDebt.due_date)
    await message.answer(
        "Qarzni qaytarish sanasini kiriting:\n"
        "— aniq sana: kun.oy.yil, masalan 25.07.2026\n"
        "— yoki necha kundan keyin: masalan 7\n"
        "— yoki sanasiz davom etish uchun '-' deb yozing",
        reply_markup=kb.skip_due_date_kb()
    )


@router.message(AddDebt.due_date)
async def add_debt_due_date(message: Message, state: FSMContext):
    try:
        due_date = _parse_due_date(message.text)
    except ValueError:
        await message.answer(
            "Iltimos, sanani to'g'ri formatda kiriting: kun.oy.yil (masalan 25.07.2026), "
            "necha kundan keyinligini son bilan (masalan 7), yoki '-' deb yozing."
        )
        return
    await state.update_data(due_date=due_date)
    await state.set_state(AddDebt.description)
    await message.answer("Izoh kiriting (masalan: 'Oziq-ovqat qarzi'):")


@router.callback_query(AddDebt.due_date, F.data == "skip_due_date")
async def add_debt_skip_due_date(callback: CallbackQuery, state: FSMContext):
    await state.update_data(due_date=None)
    await state.set_state(AddDebt.description)
    await callback.answer()
    await callback.message.answer("Izoh kiriting (masalan: 'Oziq-ovqat qarzi'):")


@router.message(AddDebt.description)
async def add_debt_description(message: Message, state: FSMContext):
    data = await state.get_data()
    debt_id = await db.add_debt(
        data["customer_name"], data["phone"], data["amount"], message.text.strip(),
        due_date=data.get("due_date"), taken_date=data.get("taken_date")
    )
    await state.clear()

    taken_dt = datetime.strptime(data["taken_date"], "%Y-%m-%d")
    taken_date_line = f"Qarz olgan sana: {taken_dt.strftime('%d.%m.%Y')}\n"

    due_date_line = ""
    if data.get("due_date"):
        due_dt = datetime.strptime(data["due_date"], "%Y-%m-%d")
        due_date_line = f"Qaytarish sanasi: {due_dt.strftime('%d.%m.%Y')}\n"

    link = await _debt_link(message.bot, debt_id)
    await message.answer(
        f"✅ Qarz qo'shildi:\n"
        f"Mijoz: {data['customer_name']}\n"
        f"Summasi: {data['amount']:.0f} so'm\n"
        f"{taken_date_line}"
        f"{due_date_line}",
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

        due_line = ""
        due_date_str = d.get("due_date")
        if due_date_str:
            try:
                due_dt = datetime.strptime(due_date_str, "%Y-%m-%d")
                days_left = (due_dt.date() - datetime.now().date()).days
                due_fmt = due_dt.strftime("%d.%m.%Y")
                if days_left < 0:
                    due_line = f"❗️ Qaytarish sanasi: {due_fmt} ({-days_left} kun kechikdi)\n"
                elif days_left == 0:
                    due_line = f"📅 Qaytarish sanasi: {due_fmt} (bugun)\n"
                else:
                    due_line = f"📅 Qaytarish sanasi: {due_fmt} ({days_left} kun qoldi)\n"
            except ValueError:
                pass

        taken_line = ""
        taken_date_str = d.get("taken_date")
        if taken_date_str:
            try:
                taken_dt = datetime.strptime(taken_date_str, "%Y-%m-%d")
                taken_line = f"🗓 Qarz olgan sana: {taken_dt.strftime('%d.%m.%Y')}\n"
            except ValueError:
                pass

        linked = bool(d.get("customer_chat_id"))
        link_line = "\n🔗 Botga ulangan (eslatma yuborish mumkin)" if linked else ""

        paid_amount = d.get("paid_amount") or 0
        if paid_amount > 0:
            remaining = d["amount"] - paid_amount
            amount_block = (
                f"💵 Jami qarz: {d['amount']:.0f} so'm\n"
                f"✅ To'landi: {paid_amount:.0f} so'm\n"
                f"❗️ Qolgan: <b>{remaining:.0f} so'm</b>\n"
            )
        else:
            amount_block = f"💵 {d['amount']:.0f} so'm\n"

        text = (
            f"👤 <b>{d['customer_name']}</b>\n"
            f"📞 {d['phone']}\n"
            f"{amount_block}"
            f"{age_line}"
            f"{taken_line}"
            f"{due_line}"
            f"📝 {d['description']}"
            f"{link_line}"
        )
        await message.answer(
            text,
            reply_markup=kb.debt_action_kb(d["id"], customer_linked=linked),
            parse_mode="HTML"
        )


@router.callback_query(F.data.startswith("pay_debt_"))
async def pay_debt_start(callback: CallbackQuery, state: FSMContext):
    debt_id = int(callback.data.split("_")[-1])
    debt = await db.get_debt(debt_id)
    if not debt:
        await callback.answer("Qarz topilmadi", show_alert=True)
        return
    if debt["is_paid"]:
        await callback.answer("Bu qarz allaqachon to'liq to'langan ✅", show_alert=True)
        return

    remaining = debt["amount"] - (debt.get("paid_amount") or 0)
    await state.update_data(debt_id=debt_id)
    await state.set_state(PayDebt.amount)
    await callback.answer()
    await callback.message.answer(
        f"👤 <b>{debt['customer_name']}</b>\n"
        f"Qolgan qarz: <b>{remaining:.0f} so'm</b>\n\n"
        f"To'lanayotgan summani kiriting (to'liq to'lash uchun {remaining:.0f} deb yozing):",
        parse_mode="HTML",
    )


@router.message(PayDebt.amount)
async def pay_debt_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", ".").replace(" ", ""))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Iltimos, musbat raqam kiriting. Masalan: 100000")
        return

    data = await state.get_data()
    debt_id = data["debt_id"]
    debt = await db.get_debt(debt_id)
    if not debt:
        await state.clear()
        await message.answer("Bu qarz topilmadi (o'chirilgan bo'lishi mumkin).")
        return

    remaining_before = debt["amount"] - (debt.get("paid_amount") or 0)
    if amount > remaining_before:
        await message.answer(
            f"Kiritilgan summa ({amount:.0f} so'm) qolgan qarzdan ({remaining_before:.0f} so'm) "
            f"katta. Iltimos, {remaining_before:.0f} so'mdan oshmaydigan summa kiriting."
        )
        return

    result = await db.add_debt_payment(debt_id, amount)
    await state.clear()

    if result["status"] == "full":
        await message.answer(
            f"✅ <b>{debt['customer_name']}</b>ning qarzi to'liq to'landi!\n"
            f"Jami to'landi: {result['paid_amount']:.0f} so'm",
            reply_markup=kb.qarz_menu(),
            parse_mode="HTML",
        )
    else:
        await message.answer(
            f"✅ To'lov qabul qilindi: {amount:.0f} so'm\n\n"
            f"👤 <b>{debt['customer_name']}</b>\n"
            f"Jami to'landi: {result['paid_amount']:.0f} so'm\n"
            f"Qolgan qarz: <b>{result['remaining']:.0f} so'm</b>",
            reply_markup=kb.qarz_menu(),
            parse_mode="HTML",
        )


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
