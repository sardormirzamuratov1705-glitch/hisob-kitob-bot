import logging

from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

import database as db
import keyboards as kb
import alerts
from access_control import get_shop_id, get_branch_id
from dedupe import user_lock, DuplicateAction

router = Router()


class AddTransaction(StatesGroup):
    amount = State()
    description = State()


class SearchSales(StatesGroup):
    query = State()


# Bu bo'lim tugmalari faqat do'kon egalariga ko'rsatiladi (bosh adminning o'z
# do'koni yo'q). Shunga qaramay, har bir handler shop_id'ni qayta tekshiradi -
# bosh admin adashib shu bo'limga kirib qolsa ham, hech qanday do'kon
# ma'lumotiga ega bo'lmaydi.

async def _require_shop(message: Message):
    shop_id = await get_shop_id(message.from_user.id)
    if shop_id is None:
        await message.answer("Bu bo'lim faqat do'kon egalari uchun.")
    return shop_id


# ---------- KIRIM ----------

@router.message(F.text == "➕ Kirim qo'shish")
async def add_income_start(message: Message, state: FSMContext):
    if await _require_shop(message) is None:
        return
    if not await db.is_owner(message.from_user.id):
        await message.answer("Bu bo'lim faqat do'kon egasi uchun.")
        return
    await state.update_data(type="income")
    await state.set_state(AddTransaction.amount)
    await message.answer("Kirim summasini kiriting (so'mda):")


# ---------- CHIQIM ----------

@router.message(F.text == "➖ Chiqim qo'shish")
async def add_expense_start(message: Message, state: FSMContext):
    if await _require_shop(message) is None:
        return
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
    shop_id = await get_shop_id(message.from_user.id)
    if shop_id is None:
        await state.clear()
        return

    try:
        async with user_lock(message.from_user.id):
            await _add_transaction_locked(message, state, shop_id)
    except DuplicateAction:
        pass


async def _add_transaction_locked(message: Message, state: FSMContext, shop_id: int):
    data = await state.get_data()
    branch_id = await get_branch_id(message.from_user.id)
    performed_by = message.from_user.id
    await db.add_transaction(
        shop_id, data["type"], data["amount"], message.text.strip(),
        branch_id=branch_id, performed_by=performed_by,
    )
    await state.clear()

    # SHUBHALI HOLATLAR - 9/10-BOSQICH: faqat "chiqim" uchun tekshiramiz
    # (5-qoida - katta chiqim - kirimga tegishli emas). Topilsa - logga
    # yoziladi VA do'kon egasiga darhol Telegram ogohlantirishi yuboriladi.
    if data["type"] == "expense":
        suspicious_flags = await alerts.evaluate_expense_suspicions(
            shop_id, data["amount"], performed_by=performed_by
        )
        if suspicious_flags:
            logging.warning(
                f"[SHUBHALI - CHIQIM] shop={shop_id}: " + " | ".join(suspicious_flags)
            )
            await alerts.send_suspicious_alert(message.bot, shop_id, suspicious_flags, "chiqim")

    label = "Kirim" if data["type"] == "income" else "Chiqim"
    is_owner = await db.is_owner(message.from_user.id)
    reply_markup = kb.kirim_chiqim_menu() if is_owner else kb.main_menu("seller")
    await message.answer(
        f"✅ {label} qo'shildi: {data['amount']:.0f} so'm\nIzoh: {message.text.strip()}",
        reply_markup=reply_markup
    )


# ---------- SAVDOLARNI QIDIRISH ----------

@router.message(F.text == "🔎 Savdolarni qidirish")
async def search_sales_start(message: Message, state: FSMContext):
    if await _require_shop(message) is None:
        return
    await state.set_state(SearchSales.query)
    await message.answer("Qidirmoqchi bo'lgan mahsulot nomini (yoki nomining bir qismini) yozing:")


@router.message(SearchSales.query)
async def search_sales_input(message: Message, state: FSMContext):
    shop_id = await get_shop_id(message.from_user.id)
    if shop_id is None:
        await state.clear()
        return

    if not message.text:
        await message.answer("Iltimos, mahsulot nomini matn ko'rinishida yozing:")
        return

    query = message.text.strip()
    await state.clear()

    rows = await db.search_sales(shop_id, query)
    if not rows:
        await message.answer(
            f"\"{query}\" bo'yicha savdo topilmadi.",
            reply_markup=kb.kirim_chiqim_menu(),
        )
        return

    # Bir xil chek (sale_id) ichidagi qatorlarni birlashtirib chiqamiz.
    sales = {}
    order = []
    for row in rows:
        sid = row["sale_id"]
        if sid not in sales:
            sales[sid] = []
            order.append(sid)
        sales[sid].append(row)

    method_map = {"naqd": "💵 Naqd", "plastik": "💳 Plastik"}
    lines = [f"🔎 \"{query}\" bo'yicha topilgan savdolar:\n"]
    for sid in order:
        items = sales[sid]
        date = items[0]["created_at"][:16]
        method = method_map.get(items[0]["payment_method"], "")
        lines.append(f"🧾 <b>#{sid}</b> — {date}" + (f" ({method})" if method else ""))
        sale_total = 0.0
        for item in items:
            line_total = item["quantity"] * item["price"]
            sale_total += line_total
            lines.append(
                f"   • {item['product_name']}: {item['quantity']:.0f} dona x "
                f"{item['price']:.0f} so'm = {line_total:.0f} so'm"
            )
        lines.append(f"   Jami: {sale_total:.0f} so'm\n")

    await message.answer(
        "\n".join(lines),
        reply_markup=kb.kirim_chiqim_menu(),
        parse_mode="HTML",
    )


# ---------- BUGUNGI HOLAT ----------

@router.message(F.text == "📈 Bugungi holat")
async def today_status(message: Message):
    shop_id = await _require_shop(message)
    if shop_id is None:
        return

    income, expense = await db.get_totals(shop_id)
    balance = income - expense
    await message.answer(
        f"📈 <b>Umumiy holat</b>\n\n"
        f"Kirim: {income:.0f} so'm\n"
        f"Chiqim: {expense:.0f} so'm\n"
        f"Balans: <b>{balance:.0f} so'm</b>",
        parse_mode="HTML"
    )
