import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

import config
import database as db
import keyboards as kb
import alerts
from access_control import get_shop_id

router = Router()


class SaleFlow(StatesGroup):
    choosing = State()
    quantity = State()
    price = State()
    payment_method = State()


# Bu bo'lim tugmalari faqat do'kon egalariga ko'rsatiladi (bosh adminning o'z
# do'koni yo'q). Shunga qaramay, har bir handler shop_id'ni qayta tekshiradi -
# bosh admin adashib shu bo'limga kirib qolsa ham, hech qanday do'kon
# ma'lumotiga ega bo'lmaydi.

async def _require_shop(message: Message):
    shop_id = await get_shop_id(message.from_user.id)
    if shop_id is None:
        await message.answer("Bu bo'lim faqat do'kon egalari uchun.")
    return shop_id


async def _require_shop_cb(callback: CallbackQuery):
    shop_id = await get_shop_id(callback.from_user.id)
    if shop_id is None:
        await callback.answer("Bu bo'lim faqat do'kon egalari uchun.", show_alert=True)
    return shop_id


# ---------- MAHSULOT TANLASH (CHECKBOX) ----------

@router.message(F.text == "🛒 Savdo")
async def sale_start(message: Message, state: FSMContext):
    shop_id = await _require_shop(message)
    if shop_id is None:
        return

    products = [p for p in await db.get_all_products(shop_id) if p["quantity"] > 0]
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
    shop_id = await _require_shop_cb(callback)
    if shop_id is None:
        return

    product_id = int(callback.data.split("_")[-1])
    data = await state.get_data()
    selected = data.get("selected", [])

    if product_id in selected:
        selected.remove(product_id)
    else:
        selected.append(product_id)
    await state.update_data(selected=selected)

    products = [p for p in await db.get_all_products(shop_id) if p["quantity"] > 0]
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
    shop_id = await _require_shop_cb(callback)
    if shop_id is None:
        return

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

    suggestions = await db.get_cross_sell_suggestions(shop_id, selected)
    if suggestions:
        lines = "\n".join(
            f"• {s['product']['name']} ({s['product']['quantity']:.0f} dona bor)"
            for s in suggestions
        )
        await callback.message.answer(
            "💡 Odatda bu tovar(lar) bilan birga quyidagilar ham sotib olinadi:\n"
            f"{lines}\n\nMijozga taklif qilib ko'ring!"
        )

    await _ask_quantity(callback.message, state)


# ---------- SON VA NARX SO'RASH (BIRMA-BIR) ----------

async def _ask_quantity(message: Message, state: FSMContext):
    # Diqqat: bu funksiyaga ba'zan callback.message (botning o'z xabari) uzatiladi,
    # shunda message.from_user - bot bo'ladi, foydalanuvchi emas. Shaxsiy chatda
    # chat.id har doim foydalanuvchining o'zi bilan bir xil bo'lgani uchun shop_id'ni
    # shu orqali aniqlaymiz.
    shop_id = await get_shop_id(message.chat.id)
    if shop_id is None:
        await state.clear()
        return

    data = await state.get_data()
    product_id = data["queue"][data["index"]]
    product = await db.get_product(shop_id, product_id)

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
    shop_id = await get_shop_id(message.from_user.id)
    if shop_id is None:
        await state.clear()
        return

    try:
        qty = float(message.text.replace(",", ".").replace(" ", ""))
    except ValueError:
        await message.answer("Iltimos, faqat raqam kiriting. Masalan: 3")
        return

    data = await state.get_data()
    product = await db.get_product(shop_id, data["current_product_id"])

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
    await message.answer(
        f"Qanchaga sotildi{hint}?",
        reply_markup=kb.sale_price_kb(product.get("sell_price"), product.get("min_price")),
    )


@router.message(SaleFlow.price)
async def sale_price_input(message: Message, state: FSMContext):
    try:
        price = float(message.text.replace(",", ".").replace(" ", ""))
    except ValueError:
        await message.answer("Iltimos, faqat raqam kiriting. Masalan: 30000")
        return

    await _record_sale_price(message, price, state)


async def _record_sale_price(target: Message, price: float, state: FSMContext) -> bool:
    """Narxni tekshiradi va saqlaydi. target - javob yozish uchun Message (matn yoki callback.message).

    target ba'zan callback.message (botning o'z xabari) bo'ladi - shuning uchun
    shop_id'ni target.from_user.id emas, target.chat.id orqali aniqlaymiz
    (shaxsiy chatda chat.id = foydalanuvchi id'si)."""
    shop_id = await get_shop_id(target.chat.id)
    data = await state.get_data()
    product = await db.get_product(shop_id, data["current_product_id"])
    if not product:
        await target.answer("❌ Mahsulot topilmadi.")
        await state.clear()
        return False

    if product.get("min_price") and price < product["min_price"]:
        await target.answer(
            f"❌ Narx eng past narxdan ({product['min_price']:.0f} so'm) past bo'lishi mumkin emas. Qaytadan kiriting:"
        )
        return False
    if price < product["price"]:
        await target.answer(
            f"❌ Narx tannarxdan ({product['price']:.0f} so'm) past bo'lishi mumkin emas, "
            f"aks holda zararga ketasiz. Qaytadan kiriting:"
        )
        return False

    results = data.get("results", [])
    results.append({
        "id": product["id"],
        "name": product["name"],
        "qty": data["current_qty"],
        "price": price,
    })
    await state.update_data(results=results)

    await _advance(target, state)
    return True


@router.callback_query(SaleFlow.price, F.data == "sale_price_sell")
async def sale_price_sell_cb(callback: CallbackQuery, state: FSMContext):
    shop_id = await _require_shop_cb(callback)
    if shop_id is None:
        return

    data = await state.get_data()
    product = await db.get_product(shop_id, data["current_product_id"])
    if not product or not product.get("sell_price"):
        await callback.answer("Savdo narxi belgilanmagan", show_alert=True)
        return
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await _record_sale_price(callback.message, product["sell_price"], state)


@router.callback_query(SaleFlow.price, F.data == "sale_price_min")
async def sale_price_min_cb(callback: CallbackQuery, state: FSMContext):
    shop_id = await _require_shop_cb(callback)
    if shop_id is None:
        return

    data = await state.get_data()
    product = await db.get_product(shop_id, data["current_product_id"])
    if not product or not product.get("min_price"):
        await callback.answer("Eng past narx belgilanmagan", show_alert=True)
        return
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await _record_sale_price(callback.message, product["min_price"], state)


@router.callback_query(SaleFlow.price, F.data == "sale_price_custom")
async def sale_price_custom_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer("Narxni kiriting:")


async def _advance(message: Message, state: FSMContext):
    data = await state.get_data()
    next_index = data["index"] + 1

    if next_index < len(data["queue"]):
        await state.update_data(index=next_index)
        await _ask_quantity(message, state)
        return

    await _ask_payment_method(message, state)


async def _ask_payment_method(message: Message, state: FSMContext):
    # Barcha mahsulotlar tanlanib, narxlari kiritib bo'lingach, to'lov turini
    # (naqd/plastik) FAQAT BIR MARTA so'raymiz - har bir mahsulot uchun emas.
    # Shu bilan birga, to'lov turini tanlashdan oldin JAMI summani ko'rsatamiz,
    # shunda sotuvchi hech qanday kalkulyatorsiz umumiy summani ko'rib,
    # keyin bitta tugma bosib to'lov turini belgilaydi.
    data = await state.get_data()
    results = data.get("results", [])

    lines = []
    total = 0.0
    for r in results:
        line_total = r["qty"] * r["price"]
        total += line_total
        lines.append(f"• {r['name']}: {r['qty']:.0f} dona x {r['price']:.0f} so'm = {line_total:.0f} so'm")

    summary = "\n".join(lines)

    await state.set_state(SaleFlow.payment_method)
    await message.answer(
        f"🧾 <b>Savdo xulosasi:</b>\n{summary}\n\n"
        f"<b>Jami: {total:.0f} so'm</b>\n\n"
        f"To'lov turi qanday bo'ldi?",
        reply_markup=kb.payment_method_kb(),
        parse_mode="HTML",
    )


@router.callback_query(SaleFlow.payment_method, F.data.startswith("pay_method_"))
async def sale_payment_method_cb(callback: CallbackQuery, state: FSMContext):
    method = callback.data.replace("pay_method_", "")  # "naqd" | "plastik"
    await state.update_data(payment_method=method)
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await _finalize_sale(callback.message, state)


# ---------- YAKUNLASH: SKLADNI KAMAYTIRISH + KIRIM YOZISH ----------

async def _finalize_sale(message: Message, state: FSMContext):
    # message bu yerda callback.message (botning o'z xabari) - shuning uchun
    # chat.id orqali shop_id aniqlanadi (from_user bot bo'lib qolgan bo'lardi).
    shop_id = await get_shop_id(message.chat.id)
    if shop_id is None:
        await state.clear()
        return

    data = await state.get_data()
    results = data.get("results", [])

    total = 0.0
    lines = []
    for r in results:
        product = await db.get_product(shop_id, r["id"])
        if not product:
            continue

        new_quantity = product["quantity"] - r["qty"]
        await db.update_product_quantity(shop_id, r["id"], new_quantity)
        await alerts.notify_stock_change(
            message.bot, shop_id, product, product["quantity"], new_quantity,
            also_notify_chat_id=message.chat.id,
        )

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
    payment_method = data.get("payment_method")
    sale_id = await db.add_transaction(shop_id, "income", total, description, payment_method=payment_method)

    for r in results:
        await db.add_sale_item(shop_id, sale_id, r["id"], r["qty"], r["price"])
        await db.mark_product_sold(shop_id, r["id"])

    await state.clear()

    method_label = {"naqd": "💵 Naqd", "plastik": "💳 Plastik"}.get(payment_method, "")
    method_line = f"\nTo'lov turi: {method_label}" if method_label else ""

    await message.answer(
        f"✅ Savdo yakunlandi!\n\n" + "\n".join(lines) + f"\n\n<b>Jami: {total:.0f} so'm</b>{method_line}",
        reply_markup=kb.kirim_chiqim_menu(),
        parse_mode="HTML"
    )
