import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

import config
import database as db
import keyboards as kb

router = Router()


class AddProduct(StatesGroup):
    name = State()
    price = State()
    sell_price = State()
    min_price = State()
    quantity = State()
    photo = State()


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
    )
    await state.clear()
    await message.answer(
        f"✅ Mahsulot qo'shildi:\n<b>{data['name']}</b>\nTannarx: {data['price']:.0f} so'm\n"
        f"Savdo narxi: {data['sell_price']:.0f} so'm\nEng past narx: {data['min_price']:.0f} so'm\n"
        f"Miqdori: {data['quantity']:.0f}",
        reply_markup=kb.sklad_menu(),
        parse_mode="HTML"
    )


@router.callback_query(AddProduct.photo, F.data == "skip_photo")
async def add_product_skip_photo(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await db.add_product(
        data["name"], data["price"], data["quantity"], None,
        sell_price=data["sell_price"], min_price=data["min_price"],
    )
    await state.clear()
    await callback.message.answer(
        f"✅ Mahsulot qo'shildi:\n<b>{data['name']}</b>\nTannarx: {data['price']:.0f} so'm\n"
        f"Savdo narxi: {data['sell_price']:.0f} so'm\nEng past narx: {data['min_price']:.0f} so'm\n"
        f"Miqdori: {data['quantity']:.0f}",
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
    product["quantity"] = new_quantity
    await _sync_after_qty_change(callback, product)


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
