import os
import shutil
from datetime import datetime

import aiosqlite
from aiogram import Router, F
from aiogram.types import Message, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

import config
import database as db
import keyboards as kb
from access_control import get_shop_id, is_admin

router = Router()


class RestoreDB(StatesGroup):
    waiting_file = State()


async def _require_shop(message: Message):
    shop_id = await get_shop_id(message.from_user.id)
    if shop_id is None:
        await message.answer("Bu bo'lim faqat do'kon egalari uchun.")
    return shop_id


@router.message(F.text == "📊 Umumiy hisobot")
async def general_report(message: Message):
    shop_id = await _require_shop(message)
    if shop_id is None:
        return

    income, expense = await db.get_totals(shop_id)
    balance = income - expense
    total_debt = await db.get_total_debt(shop_id)
    products = await db.get_all_products(shop_id)
    total_stock_value = sum(p["price"] * p["quantity"] for p in products)
    payment_totals = await db.get_payment_method_totals(shop_id, "income")

    text = (
        "📊 <b>Umumiy hisobot</b>\n\n"
        f"💰 Kirim: {income:.0f} so'm\n"
        f"   💵 Naqd: {payment_totals['naqd']:.0f} so'm\n"
        f"   💳 Plastik: {payment_totals['plastik']:.0f} so'm\n"
        f"💸 Chiqim: {expense:.0f} so'm\n"
        f"📈 Balans: <b>{balance:.0f} so'm</b>\n\n"
        f"📦 Skladdagi mahsulotlar soni: {len(products)} xil\n"
        f"📦 Sklad qiymati: {total_stock_value:.0f} so'm\n\n"
        f"📒 Umumiy qarzdorlik: {total_debt:.0f} so'm"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(F.text == "🏆 Top mahsulotlar")
async def top_products_report(message: Message):
    shop_id = await _require_shop(message)
    if shop_id is None:
        return

    top_selling = await db.get_top_selling_products(shop_id, limit=10)
    top_profit = await db.get_top_profit_products(shop_id, limit=10)

    lines = ["🏆 <b>Top 10 - eng ko'p sotilgan</b>\n"]
    if top_selling:
        for i, r in enumerate(top_selling, 1):
            lines.append(f"{i}. {r['name']} — {r['total_qty']:.0f} dona ({r['total_sum']:.0f} so'm)")
    else:
        lines.append("Ma'lumot yo'q.")

    lines.append("\n💰 <b>Top 10 - eng ko'p foyda keltirgan</b>\n")
    if top_profit:
        for i, r in enumerate(top_profit, 1):
            lines.append(f"{i}. {r['name']} — {r['total_profit']:.0f} so'm foyda")
    else:
        lines.append("Ma'lumot yo'q.")

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(F.text == "📥 Excel yuklab olish")
async def export_excel(message: Message):
    shop_id = await _require_shop(message)
    if shop_id is None:
        return

    products = await db.get_all_products(shop_id)
    transactions = await db.get_transactions(shop_id, limit=1000)
    debts = await db.get_debts(shop_id, only_unpaid=False)

    wb = Workbook()

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")

    # ---- Sklad ----
    ws1 = wb.active
    ws1.title = "Sklad"
    ws1.append(["ID", "Nomi", "Narxi", "Miqdori", "Jami qiymat", "Qo'shilgan sana"])
    for cell in ws1[1]:
        cell.font = header_font
        cell.fill = header_fill
    for p in products:
        ws1.append([
            p["id"], p["name"], p["price"], p["quantity"],
            p["price"] * p["quantity"], p["created_at"][:10]
        ])

    # ---- Kirim/Chiqim ----
    ws2 = wb.create_sheet("Kirim-Chiqim")
    ws2.append(["ID", "Turi", "Summasi", "To'lov turi", "Izoh", "Sana"])
    for cell in ws2[1]:
        cell.font = header_font
        cell.fill = header_fill
    for t in transactions:
        label = "Kirim" if t["type"] == "income" else "Chiqim"
        method_map = {"naqd": "Naqd", "plastik": "Plastik"}
        method_label = method_map.get(t.get("payment_method"), "")
        ws2.append([t["id"], label, t["amount"], method_label, t["description"], t["created_at"][:16]])

    # ---- Qarz daftar ----
    ws3 = wb.create_sheet("Qarz daftar")
    ws3.append([
        "ID", "Mijoz", "Telefon", "Qarz summasi", "To'langan", "Qolgan",
        "Izoh", "Holati", "Olingan sanasi", "Qaytarish sanasi", "Kiritilgan sana"
    ])
    for cell in ws3[1]:
        cell.font = header_font
        cell.fill = header_fill
    for d in debts:
        status = "To'landi" if d["is_paid"] else "Qarzda"
        paid_amount = d.get("paid_amount") or 0
        remaining = d["amount"] - paid_amount
        taken_date = d.get("taken_date") or d["created_at"][:10]
        due_date = d.get("due_date") or ""
        ws3.append([
            d["id"], d["customer_name"], d["phone"], d["amount"], paid_amount, remaining,
            d["description"], status, taken_date, due_date, d["created_at"][:10]
        ])

    # Ustun kengligini avtomoslashtirish
    for ws in (ws1, ws2, ws3):
        for column_cells in ws.columns:
            length = max(len(str(cell.value or "")) for cell in column_cells)
            ws.column_dimensions[column_cells[0].column_letter].width = length + 3

    filename = f"hisobot_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    filepath = f"/tmp/{filename}"
    wb.save(filepath)

    await message.answer_document(FSInputFile(filepath, filename=filename))
    os.remove(filepath)


# ---------- DB FAYLNI ZAXIRALASH / TIKLASH ----------
# Railway'da Volume ulanmagan bo'lsa, redeploy vaqtida baza tozalanadi va
# barcha do'konlarning ma'lumotlarini qaytadan kiritish kerak bo'ladi. Bu -
# BUTUN bazani (barcha do'konlar birdaniga) qamrab oladigan texnik zaxira
# vositasi, shuning uchun endi faqat BOSH ADMINGA ochiq - alohida do'kon
# egasi bunga kira olmaydi (aks holda u boshqa do'konlarning ma'lumotlarini
# ko'rib/almashtirib qo'yishi mumkin edi).

@router.message(F.text == "🗄 DB faylni yuklab olish")
async def export_db(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Bu bo'lim faqat bosh admin uchun.")
        return

    if not os.path.exists(config.DB_PATH):
        await message.answer("❌ Baza fayli topilmadi.")
        return

    filename = os.path.basename(config.DB_PATH) or "shop.db"
    await message.answer_document(
        FSInputFile(config.DB_PATH, filename=filename),
        caption=(
            "🗄 Joriy baza fayli (BARCHA do'konlar).\n"
            "Buni saqlab qo'ying — baza tozalanib qolsa (masalan redeploy'da), "
            "\"📤 DB faylni tiklash\" tugmasi orqali shu faylni qayta yuklab, "
            "barcha do'konlarni qaytadan kiritmasdan tiklashingiz mumkin."
        ),
    )


@router.message(F.text == "📤 DB faylni tiklash")
async def restore_db_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("Bu bo'lim faqat bosh admin uchun.")
        return

    await state.set_state(RestoreDB.waiting_file)
    await message.answer(
        "⚠️ <b>Diqqat!</b> Yuboradigan faylingiz joriy bazadagi BARCHA do'konlarning "
        "ma'lumotlarini (mahsulotlar, kirim-chiqim, qarzlar, do'kon egalari) to'liq almashtiradi.\n\n"
        "Avval joriy bazani zaxiralab olmoqchi bo'lsangiz, \"🗄 DB faylni yuklab olish\" "
        "tugmasini bosing.\n\n"
        "Tiklash uchun oldin saqlab qo'ygan .db faylni hujjat sifatida yuboring "
        "(bekor qilish uchun \"⬅️ Orqaga\" tugmasini bosing):",
        parse_mode="HTML",
    )


@router.message(RestoreDB.waiting_file, F.document)
async def restore_db_file(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    document = message.document
    tmp_path = f"/tmp/restore_{document.file_unique_id}.db"
    await message.bot.download(document.file_id, destination=tmp_path)

    valid = False
    try:
        async with aiosqlite.connect(tmp_path) as test_db:
            cursor = await test_db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='products'"
            )
            row = await cursor.fetchone()
            valid = row is not None
    except Exception:
        valid = False

    if not valid:
        os.remove(tmp_path)
        await message.answer(
            "❌ Bu fayl to'g'ri baza fayli emasga o'xshaydi. Qaytadan urinib ko'ring "
            "yoki \"⬅️ Orqaga\" tugmasini bosing."
        )
        return

    db_dir = os.path.dirname(config.DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    shutil.move(tmp_path, config.DB_PATH)

    await state.clear()
    await message.answer(
        "✅ Baza muvaffaqiyatli tiklandi (barcha do'konlar). Qaytadan kiritishning hojati yo'q.",
        reply_markup=kb.main_menu("admin"),
    )


@router.message(RestoreDB.waiting_file)
async def restore_db_wrong_type(message: Message):
    await message.answer(
        "Iltimos, .db faylni hujjat (document) sifatida yuboring, "
        "yoki bekor qilish uchun \"⬅️ Orqaga\" tugmasini bosing."
    )
