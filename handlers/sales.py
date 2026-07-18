import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

import config
import database as db
import keyboards as kb
import alerts
from access_control import get_shop_id, get_branch_id, get_role

router = Router()


class SaleFlow(StatesGroup):
    choosing = State()
    searching = State()
    quantity = State()
    price = State()
    payment_method = State()
    mixed_cash_amount = State()


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


async def _sellable_products(shop_id, query: str = ""):
    """Skladda bor mahsulotlar ro'yxati, kerak bo'lsa nomi bo'yicha filtrlangan."""
    products = [p for p in await db.get_all_products(shop_id) if p["quantity"] > 0]
    if query:
        q = query.strip().lower()
        products = [p for p in products if q in p["name"].lower()]
    return products


# ---------- MAHSULOT TANLASH (CHECKBOX) ----------

@router.message(F.text == "🛒 Savdo")
async def sale_start(message: Message, state: FSMContext):
    shop_id = await _require_shop(message)
    if shop_id is None:
        return

    products = await _sellable_products(shop_id)
    if not products:
        await message.answer("Skladda savdo qilish uchun mahsulot yo'q.")
        return

    await state.set_state(SaleFlow.choosing)
    await state.update_data(selected=[], page=0, search_query="")
    await message.answer(
        "Sotiladigan mahsulot(lar)ni belgilang:",
        reply_markup=kb.sale_products_kb(products, [], page=0)
    )


@router.callback_query(SaleFlow.choosing, F.data.startswith("sale_toggle_"))
async def sale_toggle(callback: CallbackQuery, state: FSMContext):
    shop_id = await _require_shop_cb(callback)
    if shop_id is None:
        return

    product_id = int(callback.data.split("_")[-1])
    data = await state.get_data()
    selected = data.get("selected", [])
    page = data.get("page", 0)
    query = data.get("search_query", "")

    if product_id in selected:
        selected.remove(product_id)
    else:
        selected.append(product_id)
    await state.update_data(selected=selected)

    products = await _sellable_products(shop_id, query)
    try:
        await callback.message.edit_reply_markup(
            reply_markup=kb.sale_products_kb(products, selected, page=page, search_active=bool(query))
        )
    except Exception:
        pass
    await callback.answer()


@router.callback_query(SaleFlow.choosing, F.data == "sale_page_next")
async def sale_page_next(callback: CallbackQuery, state: FSMContext):
    await _sale_change_page(callback, state, delta=1)


@router.callback_query(SaleFlow.choosing, F.data == "sale_page_prev")
async def sale_page_prev(callback: CallbackQuery, state: FSMContext):
    await _sale_change_page(callback, state, delta=-1)


async def _sale_change_page(callback: CallbackQuery, state: FSMContext, delta: int):
    shop_id = await _require_shop_cb(callback)
    if shop_id is None:
        return

    data = await state.get_data()
    selected = data.get("selected", [])
    query = data.get("search_query", "")
    page = data.get("page", 0) + delta
    if page < 0:
        page = 0
    await state.update_data(page=page)

    products = await _sellable_products(shop_id, query)
    try:
        await callback.message.edit_reply_markup(
            reply_markup=kb.sale_products_kb(products, selected, page=page, search_active=bool(query))
        )
    except Exception:
        pass
    await callback.answer()


@router.callback_query(SaleFlow.choosing, F.data == "sale_noop")
async def sale_noop(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(SaleFlow.choosing, F.data == "sale_search")
async def sale_search_start(callback: CallbackQuery, state: FSMContext):
    shop_id = await _require_shop_cb(callback)
    if shop_id is None:
        return

    await state.set_state(SaleFlow.searching)
    await callback.answer()
    await callback.message.answer("Mahsulot nomini (yoki nomining bir qismini) yozing:")


@router.message(SaleFlow.searching)
async def sale_search_input(message: Message, state: FSMContext):
    shop_id = await get_shop_id(message.from_user.id)
    if shop_id is None:
        await state.clear()
        return

    if not message.text:
        await message.answer("Iltimos, mahsulot nomini matn ko'rinishida yozing:")
        return

    query = message.text.strip()
    data = await state.get_data()
    selected = data.get("selected", [])

    products = await _sellable_products(shop_id, query)
    await state.update_data(search_query=query, page=0)
    await state.set_state(SaleFlow.choosing)

    if not products:
        await message.answer(
            f"\"{query}\" bo'yicha mahsulot topilmadi. Boshqa nom bilan qidiring yoki qidiruvni bekor qiling:",
            reply_markup=kb.sale_products_kb([], selected, page=0, search_active=True)
        )
        return

    await message.answer(
        f"🔎 \"{query}\" bo'yicha natijalar:",
        reply_markup=kb.sale_products_kb(products, selected, page=0, search_active=True)
    )


@router.callback_query(SaleFlow.choosing, F.data == "sale_search_clear")
async def sale_search_clear(callback: CallbackQuery, state: FSMContext):
    shop_id = await _require_shop_cb(callback)
    if shop_id is None:
        return

    data = await state.get_data()
    selected = data.get("selected", [])
    await state.update_data(search_query="", page=0)

    products = await _sellable_products(shop_id)
    try:
        await callback.message.edit_text(
            "Sotiladigan mahsulot(lar)ni belgilang:",
            reply_markup=kb.sale_products_kb(products, selected, page=0)
        )
    except Exception:
        try:
            await callback.message.edit_reply_markup(
                reply_markup=kb.sale_products_kb(products, selected, page=0)
            )
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
    # "🛒 Savdo" endi Kirim/Chiqim ichida emas, asosiy menyuda mustaqil tugma -
    # shuning uchun bekor qilingach ham asosiy menyuga qaytariladi.
    role = await get_role(callback.from_user.id)
    await callback.message.answer("Savdo bekor qilindi.", reply_markup=kb.main_menu(role))


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
    discount = db.product_discount_info(product)
    await message.answer(
        f"Qanchaga sotildi{hint}?",
        reply_markup=kb.sale_price_kb(
            product.get("sell_price"),
            product.get("min_price"),
            discount["price"] if discount else None,
        ),
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

    # Chegirma faol bo'lgan mahsulotlarda "eng past narx" cheklovi
    # vaqtincha bekor qilinadi - chegirma summasi eng past narxdan past
    # yoki teng bo'lsa ham sotishga xalal bermasligi kerak. Tannarxdan
    # (zararga sotmaslik) past narx esa har doim, chegirma bor-yo'qligidan
    # qat'i nazar, taqiqlanadi. Chegirma muddati tugagach - eng past narx
    # cheklovi avtomatik yana ishlay boshlaydi (db.product_discount_info()
    # o'sha payt None qaytaradi).
    has_active_discount = bool(db.product_discount_info(product))

    if product.get("min_price") and price < product["min_price"] and not has_active_discount:
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


@router.callback_query(SaleFlow.price, F.data == "sale_price_discount")
async def sale_price_discount_cb(callback: CallbackQuery, state: FSMContext):
    shop_id = await _require_shop_cb(callback)
    if shop_id is None:
        return

    data = await state.get_data()
    product = await db.get_product(shop_id, data["current_product_id"])
    discount = db.product_discount_info(product) if product else None
    if not discount:
        await callback.answer("Chegirma muddati tugagan yoki bekor qilingan", show_alert=True)
        return
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await _record_sale_price(callback.message, discount["price"], state)


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
    method = callback.data.replace("pay_method_", "")  # "naqd" | "plastik" | "aralash"
    await callback.answer()

    if method == "aralash":
        data = await state.get_data()
        total = sum(r["qty"] * r["price"] for r in data.get("results", []))
        await state.update_data(payment_method=method, mixed_total=total)
        await state.set_state(SaleFlow.mixed_cash_amount)
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(
            f"Jami: {total:.0f} so'm.\nShundan qanchasi <b>naqd</b> to'landi (so'mda)?",
            parse_mode="HTML",
        )
        return

    await state.update_data(payment_method=method)
    try:
        await callback.message.delete()
    except Exception:
        pass
    await _finalize_sale(callback.message, state)


@router.message(SaleFlow.mixed_cash_amount)
async def sale_mixed_cash_amount(message: Message, state: FSMContext):
    try:
        cash = float(message.text.replace(",", ".").replace(" ", ""))
    except ValueError:
        await message.answer("Iltimos, faqat raqam kiriting. Masalan: 50000")
        return

    data = await state.get_data()
    total = data.get("mixed_total", 0.0)
    if cash < 0 or cash > total:
        await message.answer(
            f"Naqd summasi 0 dan {total:.0f} so'mgacha bo'lishi kerak. Qaytadan kiriting:"
        )
        return

    card = total - cash
    await state.update_data(mixed_cash=cash, mixed_card=card)
    await _finalize_sale(message, state)


# ---------- YAKUNLASH: SKLADNI KAMAYTIRISH + KIRIM YOZISH ----------

async def _finalize_sale(message: Message, state: FSMContext):
    # message bu yerda callback.message (botning o'z xabari) - shuning uchun
    # chat.id orqali shop_id aniqlanadi (from_user bot bo'lib qolgan bo'lardi).
    # xuddi shu sababdan "amalni bajargan" sifatida ham chat.id ishlatiladi
    # (shaxsiy chatda chat.id == shu odamning telegram_id'si).
    shop_id = await get_shop_id(message.chat.id)
    if shop_id is None:
        await state.clear()
        return

    performed_by = message.chat.id
    data = await state.get_data()
    results = data.get("results", [])

    total = 0.0
    lines = []
    sale_lines = []
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
        # SHUBHALI HOLATLAR - 9-BOSQICH: tekshiruv uchun SOTUVDAN OLDINGI
        # product holatini saqlab qo'yamiz (product["quantity"] hali eski).
        sale_lines.append({"product": product, "quantity": r["qty"], "price": r["price"]})

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
    branch_id = await get_branch_id(message.chat.id)

    if payment_method == "aralash":
        cash = data.get("mixed_cash", 0.0)
        card = data.get("mixed_card", 0.0)
        if cash > 0:
            sale_id = await db.add_transaction(
                shop_id, "income", cash, description, payment_method="naqd",
                branch_id=branch_id, performed_by=performed_by,
            )
            if card > 0:
                await db.add_transaction(
                    shop_id, "income", card,
                    description + "\n(aralash to'lovning plastik qismi)",
                    payment_method="plastik", branch_id=branch_id, performed_by=performed_by,
                )
        else:
            sale_id = await db.add_transaction(
                shop_id, "income", card, description, payment_method="plastik",
                branch_id=branch_id, performed_by=performed_by,
            )
    else:
        sale_id = await db.add_transaction(
            shop_id, "income", total, description, payment_method=payment_method,
            branch_id=branch_id, performed_by=performed_by,
        )

    for r in results:
        await db.add_sale_item(shop_id, sale_id, r["id"], r["qty"], r["price"], performed_by=performed_by)
        await db.mark_product_sold(shop_id, r["id"])

    # SHUBHALI HOLATLAR - 9/10-BOSQICH: real vaqtda tekshiruv + topilsa
    # do'kon egasiga darhol Telegram ogohlantirishi (loglash bilan bir
    # qatorda - owner o'zining xabarlarini o'chirib qo'ygan bo'lsa ham,
    # logda iz qolaveradi).
    suspicious_flags = await alerts.evaluate_sale_suspicions(shop_id, sale_lines, performed_by=performed_by)
    if suspicious_flags:
        logging.warning(
            f"[SHUBHALI - SAVDO] shop={shop_id} sale_id={sale_id}: " + " | ".join(suspicious_flags)
        )
        await alerts.send_suspicious_alert(message.bot, shop_id, suspicious_flags, "savdo")

    await state.clear()

    if payment_method == "aralash":
        cash = data.get("mixed_cash", 0.0)
        card = data.get("mixed_card", 0.0)
        method_line = f"\nTo'lov turi: 🔀 Aralash (💵 {cash:.0f} so'm + 💳 {card:.0f} so'm)"
    else:
        method_label = {"naqd": "💵 Naqd", "plastik": "💳 Plastik"}.get(payment_method, "")
        method_line = f"\nTo'lov turi: {method_label}" if method_label else ""

    # "🛒 Savdo" endi Kirim/Chiqim ichida emas, asosiy menyuda mustaqil tugma -
    # shuning uchun savdo yakunlangach ham asosiy menyuga qaytariladi.
    role = await get_role(message.chat.id)
    await message.answer(
        f"✅ Savdo yakunlandi!\n\n" + "\n".join(lines) + f"\n\n<b>Jami: {total:.0f} so'm</b>{method_line}",
        reply_markup=kb.main_menu(role),
        parse_mode="HTML"
    )
