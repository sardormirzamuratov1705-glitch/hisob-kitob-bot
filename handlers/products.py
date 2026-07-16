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
    await message.answer("Narxini kiriting (so'mda, faqat raqam):")


@router.message(AddProduct.price)
async def add_product_price(message: Message, state: FSMContext):
    try:
        price = float(message.text.replace(",", ".").replace(" ", ""))
    except ValueError:
        await message.answer("Iltimos, faqat raqam kiriting. Masalan: 25000")
        return
    await state.update_data(price=price)
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

    # Rasmni kanalga jo'natib, o'sha yerdagi file_id'ni olamiz.
    # Shunda rasm botning o'z serverida emas, Telegram kanalida saqlanadi
    # va foydalanuvchi bot bilan chatni o'chirsa ham rasm yo'qolmaydi.
    if config.CHANNEL_ID:
        try:
            sent = await message.bot.send_photo(
                chat_id=config.CHANNEL_ID,
                photo=photo_file_id,
                caption=f"🆕 {data['name']} | {data['price']:.0f} so'm | {data['quantity']:.0f} dona",
            )
            photo_file_id = sent.photo[-1].file_id
        except Exception as e:
            logging.warning(f"Rasmni kanalga yuborib bo'lmadi: {e}")

    await db.add_product(data["name"], data["price"], data["quantity"], photo_file_id)
    await state.clear()
    await message.answer(
        f"✅ Mahsulot qo'shildi:\n<b>{data['name']}</b>\nNarxi: {data['price']:.0f} so'm\n"
        f"Miqdori: {data['quantity']:.0f}",
        reply_markup=kb.sklad_menu(),
        parse_mode="HTML"
    )


@router.callback_query(AddProduct.photo, F.data == "skip_photo")
async def add_product_skip_photo(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await db.add_product(data["name"], data["price"], data["quantity"], None)
    await state.clear()
    await callback.message.answer(
        f"✅ Mahsulot qo'shildi:\n<b>{data['name']}</b>\nNarxi: {data['price']:.0f} so'm\n"
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
            f"Narxi: {p['price']:.0f} so'm\n"
            f"Miqdori: {p['quantity']:.0f}"
        )
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
    await db.delete_product(product_id)
    await callback.answer("Mahsulot o'chirildi ✅")
    try:
        await callback.message.delete()
    except Exception:
        pass
