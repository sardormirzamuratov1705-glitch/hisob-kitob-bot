import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

import config
import database as db
import keyboards as kb
import alerts

router = Router()


class AddProduct(StatesGroup):
    name = State()
    price = State()
    sell_price = State()
    min_price = State()
    quantity = State()
    alert_quantity = State()
    photo = State()


class AddRestockItem(StatesGroup):
    name = State()
    note = State()


# ---------- MAHSULOT QO'SHISH ----------

@router.message(F.text == "➕ Mahsulot qo'shish")
async def add_product_start(message: Message, state: FSMContext):
    await state.set_state(AddProduct.name)
    await message.answer("Mahsulot nomini kiriting:")


@router.message(AddProduct.name)
async def add_product_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(AddProduct.price)
    await message.answer("Tannarxini kiriting (necha so'mga tushdi, faqat raqam):")


@router.message(AddProduct.price)
async def add_product_price(message: Message, state: FSMContext):
    try:
        price = float(message.text.replace(",", ".").replace(" ", ""))
    except ValueError:
        await message.answer("Iltimos, faqat raqam kiriting. Masalan: 25000")
        return
    await state.update_data(price=price)
    await state.set_state(AddProduct.sell_price)
    await message.answer("Savdo narxini kiriting (necha so'mga sotasiz):")


@router.message(AddProduct.sell_price)
async def add_product_sell_price(message: Message, state: FSMContext):
    try:
        sell_price = float(message.text.replace(",", ".").replace(" ", ""))
    except ValueError:
        await message.answer("Iltimos, faqat raqam kiriting. Masalan: 30000")
        return
    data = await state.get_data()
    if sell_price < data["price"]:
        await message.answer(
            f"❌ Savdo narxi tannarxdan ({data['price']:.0f} so'm) past bo'lishi mumkin emas, "
            f"aks holda zararga ketasiz. Qaytadan kiriting:"
        )
        return
    await state.update_data(sell_price=sell_price)
    await state.set_state(AddProduct.min_price)
    await message.answer("Eng past narxini kiriting (qanchagacha tushirib berish mumkin):")


@router.message(AddProduct.min_price)
async def add_product_min_price(message: Message, state: FSMContext):
    try:
        min_price = float(message.text.replace(",", ".").replace(" ", ""))
    except ValueError:
        await message.answer("Iltimos, faqat raqam kiriting. Masalan: 27000")
        return
    data = await state.get_data()
    if min_price > data["sell_price"]:
        await message.answer(
            f"Eng past narx savdo narxidan ({data['sell_price']:.0f} so'm) katta bo'lmasligi kerak. Qaytadan kiriting:"
        )
        return
    if min_price < data["price"]:
        await message.answer(
            f"❌ Eng past narx tannarxdan ({data['price']:.0f} so'm) past bo'lishi mumkin emas, "
            f"aks holda chegirmada zararga ketasiz. Qaytadan kiriting:"
        )
        return
    await state.update_data(min_price=min_price)
    await state.set_state(AddProduct.quantity)
    await message.answer("Miqdorini kiriting (masalan: 10):")


@router.message(AddProduct.quantity)
async def add_product_quantity(message: Message, state: FSMContext):
    try:
        quantity = float(message.text.replace(",", ".").replace(" ", ""))
    except ValueError:
        await message.answer("Iltimos, faqat raqam kiriting. Masalan: 10")
        return
    await state.update_data(quantity=quantity)
    await state.set_state(AddProduct.alert_quantity)
    await message.answer(
        "Mahsulot nechta qolganda ogohlantirish yuborilsin?\n"
        "(Kerak bo'lmasa 0 deb yozing)"
    )


@router.message(AddProduct.alert_quantity)
async def add_product_alert_quantity(message: Message, state: FSMContext):
    try:
        alert_quantity = float(message.text.replace(",", ".").replace(" ", ""))
    except ValueError:
        await message.answer("Iltimos, faqat raqam kiriting. Masalan: 5 (kerak bo'lmasa 0)")
        return
    await state.update_data(alert_quantity=alert_quantity if alert_quantity > 0 else None)
    await state.set_state(AddProduct.photo)
    await message.answer(
        "Mahsulot rasmini yuboring (yoki rasmsiz davom eting):",
        reply_markup=kb.skip_photo_kb()
    )


@router.message(AddProduct.photo, F.photo)
async def add_product_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    photo_file_id = message.photo[-1].file_id
    channel_message_id = None

    # Rasmni kanalga jo'natib, o'sha yerdagi file_id va message_id'ni olamiz.
    # Shunda rasm botning o'z serverida emas, Telegram kanalida saqlanadi
    # va foydalanuvchi bot bilan chatni o'chirsa ham rasm yo'qolmaydi.
    # message_id'ni saqlab qo'yamiz - mahsulot o'chirilsa yoki miqdori
    # o'zgarsa, kanaldagi postni ham shu orqali yangilaymiz.
    if config.CHANNEL_ID:
        try:
            sent = await message.bot.send_photo(
                chat_id=config.CHANNEL_ID,
                photo=photo_file_id,
                caption=(
                    f"🆕 {data['name']} | Savdo narxi: {data['sell_price']:.0f} so'm | "
                    f"{data['quantity']:.0f} dona"
                ),
            )
            photo_file_id = sent.photo[-1].file_id
            channel_message_id = sent.message_id
        except Exception as e:
            logging.warning(f"Rasmni kanalga yuborib bo'lmadi: {e}")

    await db.add_product(
        data["name"], data["price"], data["quantity"], photo_file_id, channel_message_id,
        sell_price=data["sell_price"], min_price=data["min_price"],
        alert_quantity=data.get("alert_quantity"),
    )
    await state.clear()
    alert_line = ""
    if data.get("alert_quantity"):
        alert_line = f"Ogohlantirish chegarasi: {data['alert_quantity']:.0f} dona\n"
    await message.answer(
        f"✅ Mahsulot qo'shildi:\n<b>{data['name']}</b>\nTannarx: {data['price']:.0f} so'm\n"
        f"Savdo narxi: {data['sell_price']:.0f} so'm\nEng past narx: {data['min_price']:.0f} so'm\n"
        f"Miqdori: {data['quantity']:.0f}\n{alert_line}",
        reply_markup=kb.sklad_menu(),
        parse_mode="HTML"
    )


@router.callback_query(AddProduct.photo, F.data == "skip_photo")
async def add_product_skip_photo(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await db.add_product(
        data["name"], data["price"], data["quantity"], None,
        sell_price=data["sell_price"], min_price=data["min_price"],
        alert_quantity=data.get("alert_quantity"),
    )
    await state.clear()
    alert_line = ""
    if data.get("alert_quantity"):
        alert_line = f"Ogohlantirish chegarasi: {data['alert_quantity']:.0f} dona\n"
    await callback.message.answer(
        f"✅ Mahsulot qo'shildi:\n<b>{data['name']}</b>\nTannarx: {data['price']:.0f} so'm\n"
        f"Savdo narxi: {data['sell_price']:.0f} so'm\nEng past narx: {data['min_price']:.0f} so'm\n"
        f"Miqdori: {data['quantity']:.0f}\n{alert_line}",
        reply_markup=kb.sklad_menu(),
        parse_mode="HTML"
    )
    await callback.answer()


# ---------- MAHSULOTLAR RO'YXATI ----------

@router.message(F.text == "📋 Mahsulotlar ro'yxati")
async def list_products(message: Message):
    products = await db.get_all_products()
    if not products:
        await message.answer("Sklad hozircha bo'sh.")
        return

    for p in products:
        caption = (
            f"<b>{p['name']}</b>\n"
            f"Tannarx: {p['price']:.0f} so'm\n"
        )
        if p.get("sell_price"):
            caption += f"Savdo narxi: {p['sell_price']:.0f} so'm\n"
        if p.get("min_price"):
            caption += f"Eng past narx: {p['min_price']:.0f} so'm\n"
        caption += f"Miqdori: {p['quantity']:.0f}"
        if p.get("alert_quantity"):
            caption += f"\nOgohlantirish chegarasi: {p['alert_quantity']:.0f} dona"
        if p["photo_file_id"]:
            await message.answer_photo(
                photo=p["photo_file_id"],
                caption=caption,
                reply_markup=kb.product_action_kb(p["id"]),
                parse_mode="HTML"
            )
        else:
            await message.answer(
                caption,
                reply_markup=kb.product_action_kb(p["id"]),
                parse_mode="HTML"
            )


@router.callback_query(F.data.startswith("del_product_"))
async def delete_product_cb(callback: CallbackQuery):
    product_id = int(callback.data.split("_")[-1])
    product = await db.get_product(product_id)

    await db.delete_product(product_id)

    # Kanaldagi rasm postini ham o'chiramiz.
    if product and product.get("channel_message_id") and config.CHANNEL_ID:
        try:
            await callback.bot.delete_message(
                chat_id=config.CHANNEL_ID,
                message_id=product["channel_message_id"],
            )
        except Exception as e:
            logging.warning(f"Kanaldagi postni o'chirib bo'lmadi: {e}")

    await callback.answer("Mahsulot o'chirildi ✅")
    try:
        await callback.message.delete()
    except Exception:
        pass


# ---------- MIQDORNI O'ZGARTIRISH ----------

async def _channel_caption(product: dict) -> str:
    return f"📦 {product['name']} | {product['price']:.0f} so'm | {product['quantity']:.0f} dona"


@router.callback_query(F.data.startswith("inc_qty_"))
async def increase_qty_cb(callback: CallbackQuery):
    product_id = int(callback.data.split("_")[-1])
    product = await db.get_product(product_id)
    if not product:
        await callback.answer("Mahsulot topilmadi", show_alert=True)
        return

    new_quantity = product["quantity"] + 1
    await db.update_product_quantity(product_id, new_quantity)
    product["quantity"] = new_quantity
    await _sync_after_qty_change(callback, product)


@router.callback_query(F.data.startswith("dec_qty_"))
async def decrease_qty_cb(callback: CallbackQuery):
    product_id = int(callback.data.split("_")[-1])
    product = await db.get_product(product_id)
    if not product:
        await callback.answer("Mahsulot topilmadi", show_alert=True)
        return

    if product["quantity"] <= 0:
        await callback.answer("Miqdor 0 dan kam bo'lishi mumkin emas", show_alert=True)
        return

    new_quantity = product["quantity"] - 1
    await db.update_product_quantity(product_id, new_quantity)
    old_quantity = product["quantity"]
    product["quantity"] = new_quantity
    await _sync_after_qty_change(callback, product)
    await alerts.notify_stock_change(
        callback.bot, product, old_quantity, new_quantity,
        also_notify_chat_id=callback.from_user.id,
    )


async def _sync_after_qty_change(callback: CallbackQuery, product: dict):
    caption = (
        f"<b>{product['name']}</b>\n"
        f"Tannarx: {product['price']:.0f} so'm\n"
        f"Miqdori: {product['quantity']:.0f}"
    )
    try:
        if callback.message.photo:
            await callback.message.edit_caption(caption=caption, reply_markup=kb.product_action_kb(product["id"]), parse_mode="HTML")
        else:
            await callback.message.edit_text(caption, reply_markup=kb.product_action_kb(product["id"]), parse_mode="HTML")
    except Exception:
        pass

    if product.get("channel_message_id") and config.CHANNEL_ID:
        try:
            await callback.bot.edit_message_caption(
                chat_id=config.CHANNEL_ID,
                message_id=product["channel_message_id"],
                caption=await _channel_caption(product),
            )
        except Exception as e:
            logging.warning(f"Kanaldagi postni yangilab bo'lmadi: {e}")

    await callback.answer()


# ---------- OLINISHI KERAK BO'LGAN TOVARLAR ----------

@router.message(F.text == "🧾 Olinishi kerak bo'lgan tovarlar")
async def restock_list(message: Message, state: FSMContext):
    await state.clear()
    low_stock = await db.get_low_stock_products()
    manual_items = await db.get_manual_restock_items()

    if not low_stock and not manual_items:
        await message.answer(
            "✅ Hozircha olinishi kerak bo'lgan tovar yo'q.\n"
            "Kerak bo'lsa, pastdagi tugma orqali qo'lda qo'shishingiz mumkin.",
            reply_markup=kb.restock_kb(manual_items),
        )
        return

    text = "🧾 <b>Olinishi kerak bo'lgan tovarlar</b>\n\n"
    if low_stock:
        text += "📉 <b>Skladda kamayib qolgan (avtomatik):</b>\n"
        for p in low_stock:
            text += (
                f"• {p['name']} — {p['quantity']:.0f} dona qoldi "
                f"(chegara: {p['alert_quantity']:.0f})\n"
            )
        text += "\n"
    if manual_items:
        text += "✍️ <b>Qo'lda qo'shilgan:</b>\n"
        for item in manual_items:
            note = f" — {item['note']}" if item.get("note") else ""
            text += f"• {item['name']}{note}\n"

    await message.answer(text, reply_markup=kb.restock_kb(manual_items), parse_mode="HTML")


@router.callback_query(F.data == "restock_add")
async def restock_add_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddRestockItem.name)
    await callback.message.answer("Olinishi kerak bo'lgan tovar nomini kiriting:")
    await callback.answer()


@router.message(AddRestockItem.name)
async def restock_add_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(AddRestockItem.note)
    await message.answer("Izoh qoldirasizmi? (kerak bo'lmasa \"-\" deb yozing)")


@router.message(AddRestockItem.note)
async def restock_add_note(message: Message, state: FSMContext):
    note = message.text.strip()
    if note == "-":
        note = None
    data = await state.get_data()
    await db.add_manual_restock_item(data["name"], note)
    await state.clear()
    await message.answer(
        f"✅ \"{data['name']}\" olinishi kerak bo'lgan tovarlar ro'yxatiga qo'shildi.",
        reply_markup=kb.sklad_menu(),
    )


@router.callback_query(F.data.startswith("restock_done_"))
async def restock_done_cb(callback: CallbackQuery):
    item_id = int(callback.data.split("_")[-1])
    await db.delete_manual_restock_item(item_id)
    await callback.answer("Olindi deb belgilandi ✅")
    try:
        await callback.message.delete()
    except Exception:
        pass
