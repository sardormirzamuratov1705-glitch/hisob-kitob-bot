import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

import config
import database as db
import keyboards as kb

router = Router()


class SaleFlow(StatesGroup):
    choosing = State()
    quantity = State()
    price = State()


# ---------- MAHSULOT TANLASH (CHECKBOX) ----------

@router.message(F.text == "🛒 Savdo")
async def sale_start(message: Message, state: FSMContext):
    products = [p for p in await db.get_all_products() if p["quantity"] > 0]
    if not products:
        await message.answer("Skladda savdo qilish uchun mahsulot yo'q.")
        return

    await state.set_state(SaleFlow.choosing)
    await state.update_data(selected=[])
    await message.answer(
        "Sotiladigan mahsulot(lar)ni belgilang:",
        reply_markup=kb.sale_products_kb(products, [])
    )


@router.callback_query(SaleFlow.choosing, F.data.startswith("sale_toggle_"))
async def sale_toggle(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split("_")[-1])
    data = await state.get_data()
    selected = data.get("selected", [])

    if product_id in selected:
        selected.remove(product_id)
    else:
        selected.append(product_id)
    await state.update_data(selected=selected)

    products = [p for p in await db.get_all_products() if p["quantity"] > 0]
    try:
        await callback.message.edit_reply_markup(reply_markup=kb.sale_products_kb(products, selected))
    except Exception:
        pass
    await callback.answer()


@router.callback_query(SaleFlow.choosing, F.data == "sale_cancel")
async def sale_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer("Bekor qilindi")
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer("Savdo bekor qilindi.", reply_markup=kb.kirim_chiqim_menu())


@router.callback_query(SaleFlow.choosing, F.data == "sale_confirm")
async def sale_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get("selected", [])
    if not selected:
        await callback.answer("Kamida bitta mahsulot belgilang", show_alert=True)
        return

    await state.update_data(queue=selected, index=0, results=[])
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer()
    await _ask_quantity(callback.message, state)


# ---------- SON VA NARX SO'RASH (BIRMA-BIR) ----------

async def _ask_quantity(message: Message, state: FSMContext):
    data = await state.get_data()
    product_id = data["queue"][data["index"]]
    product = await db.get_product(product_id)

    if not product or product["quantity"] <= 0:
        await _advance(message, state)
        return

    await state.update_data(current_product_id=product_id)
    await state.set_state(SaleFlow.quantity)
    await message.answer(
        f"<b>{product['name']}</b> — skladda {product['quantity']:.0f} dona bor.\n"
        f"Nechta sotildi?",
        parse_mode="HTML"
    )


@router.message(SaleFlow.quantity)
async def sale_quantity_input(message: Message, state: FSMContext):
    try:
        qty = float(message.text.replace(",", ".").replace(" ", ""))
    except ValueError:
        await message.answer("Iltimos, faqat raqam kiriting. Masalan: 3")
        return

    data = await state.get_data()
    product = await db.get_product(data["current_product_id"])

    if qty <= 0:
        await message.answer("Miqdor 0 dan katta bo'lishi kerak. Qaytadan kiriting:")
        return
    if qty > product["quantity"]:
        await message.answer(
            f"Skladda faqat {product['quantity']:.0f} dona bor. Qaytadan kiriting:"
        )
        return

    await state.update_data(current_qty=qty)
    await state.set_state(SaleFlow.price)

    hint = ""
    if product.get("sell_price"):
        hint = f" (odatiy savdo narxi: {product['sell_price']:.0f} so'm)"
    await message.answer(f"Qanchaga sotildi{hint}?")


@router.message(SaleFlow.price)
async def sale_price_input(message: Message, state: FSMContext):
    try:
        price = float(message.text.replace(",", ".").replace(" ", ""))
    except ValueError:
        await message.answer("Iltimos, faqat raqam kiriting. Masalan: 30000")
        return

    data = await state.get_data()
    product = await db.get_product(data["current_product_id"])

    if product.get("min_price") and price < product["min_price"]:
        await message.answer(
            f"❌ Narx eng past narxdan ({product['min_price']:.0f} so'm) past bo'lishi mumkin emas. Qaytadan kiriting:"
        )
        return

    results = data.get("results", [])
    results.append({
        "id": product["id"],
        "name": product["name"],
        "qty": data["current_qty"],
        "price": price,
    })
    await state.update_data(results=results)

    await _advance(message, state)


async def _advance(message: Message, state: FSMContext):
    data = await state.get_data()
    next_index = data["index"] + 1

    if next_index < len(data["queue"]):
        await state.update_data(index=next_index)
        await _ask_quantity(message, state)
        return

    await _finalize_sale(message, state)


# ---------- YAKUNLASH: SKLADNI KAMAYTIRISH + KIRIM YOZISH ----------

async def _finalize_sale(message: Message, state: FSMContext):
    data = await state.get_data()
    results = data.get("results", [])

    total = 0.0
    lines = []
    for r in results:
        product = await db.get_product(r["id"])
        if not product:
            continue

        new_quantity = product["quantity"] - r["qty"]
        await db.update_product_quantity(r["id"], new_quantity)

        # Kanaldagi postni ham yangilaymiz.
        if product.get("channel_message_id") and config.CHANNEL_ID:
            try:
                caption = f"📦 {product['name']} | {new_quantity:.0f} dona qoldi"
                await message.bot.edit_message_caption(
                    chat_id=config.CHANNEL_ID,
                    message_id=product["channel_message_id"],
                    caption=caption,
                )
            except Exception as e:
                logging.warning(f"Kanaldagi postni yangilab bo'lmadi: {e}")

        line_total = r["qty"] * r["price"]
        total += line_total
        lines.append(f"• {r['name']}: {r['qty']:.0f} dona x {r['price']:.0f} so'm = {line_total:.0f} so'm")

    description = "Savdo:\n" + "\n".join(lines)
    await db.add_transaction("income", total, description)

    await state.clear()
    await message.answer(
        f"✅ Savdo yakunlandi!\n\n" + "\n".join(lines) + f"\n\n<b>Jami: {total:.0f} so'm</b>",
        reply_markup=kb.kirim_chiqim_menu(),
        parse_mode="HTML"
    )
