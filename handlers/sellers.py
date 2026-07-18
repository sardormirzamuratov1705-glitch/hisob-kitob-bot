from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

import database as db
import keyboards as kb
from access_control import is_admin, get_branch_id

router = Router()


class AddSeller(StatesGroup):
    waiting_input = State()


# MUHIM: bu bo'lim tugmasi faqat HAQIQIY do'kon egasiga ko'rsatiladi
# (handlers/start.py -> kb.main_menu), lekin har bir handler ichida ham
# db.is_owner() bilan qayta tekshiramiz - na bosh admin, na sotuvchi shu
# bo'limga boshqa yo'l bilan (masalan eski chatdan matnni qayta yuborib)
# kira olmasligi uchun. Sotuvchi o'ziga o'xshagan boshqa sotuvchi qo'sha
# olmaydi - faqat do'kon egasining o'zi buni qila oladi.

async def _require_owner(message: Message):
    if not await db.is_owner(message.from_user.id):
        await message.answer("Bu bo'lim faqat do'kon egasi uchun.")
        return None
    return message.from_user.id  # owner uchun shop_id = o'z telegram_id'si


@router.message(F.text == "🧑‍💼 Sotuvchilar")
async def open_sellers(message: Message, state: FSMContext):
    await state.clear()
    if await _require_owner(message) is None:
        return
    await message.answer("Sotuvchilar bo'limi:", reply_markup=kb.sellers_menu())


@router.message(F.text == "➕ Sotuvchi qo'shish")
async def add_seller_start(message: Message, state: FSMContext):
    if await _require_owner(message) is None:
        return
    await state.set_state(AddSeller.waiting_input)
    await message.answer(
        "Yangi sotuvchini qo'shish uchun:\n\n"
        "• uning istalgan xabarini shu yerga forward qiling,\n"
        "yoki\n"
        "• uning Telegram ID raqamini yuboring (masalan, @userinfobot orqali bilib olishi mumkin)."
    )


# ---------- BIR MARTALIK TAKLIF LINKI ----------
# owner uchun /users.py'dagi "Bir martalik link"ka o'xshaydi, lekin bu link
# FAQAT shu do'kon egasining o'z do'koniga sotuvchi qo'shadi (shop_id token
# bilan birga saqlanadi).

@router.message(F.text == "🔗 Sotuvchi uchun link")
async def create_seller_invite_link(message: Message):
    shop_id = await _require_owner(message)
    if shop_id is None:
        return

    token = await db.create_seller_invite(shop_id, message.from_user.id, branch_id=await get_branch_id(shop_id))
    me = await message.bot.get_me()
    link = f"https://t.me/{me.username}?start=seller_{token}"

    await message.answer(
        "🔗 Sotuvchi uchun bir martalik taklif linki tayyor:\n\n"
        f"{link}\n\n"
        "Buni yangi sotuvchiga yuboring. U linkni bosib botni ochishi bilanoq "
        "avtomatik sizning do'koningizga sotuvchi sifatida qo'shiladi.\n\n"
        "⚠️ Link faqat BITTA marta ishlaydi — birinchi bosgan odam uchun. "
        "Agar boshqa birov ham shu linkni keyinroq bossa, unga \"link band\" "
        "deb xabar beriladi.",
        reply_markup=kb.sellers_menu(),
    )


@router.message(AddSeller.waiting_input)
async def add_seller_finish(message: Message, state: FSMContext):
    shop_id = await _require_owner(message)
    if shop_id is None:
        await state.clear()
        return

    target_id = None
    full_name = None
    username = None

    if message.forward_from:
        target_id = message.forward_from.id
        full_name = message.forward_from.full_name
        username = message.forward_from.username
    elif message.text and message.text.strip().lstrip("-").isdigit():
        target_id = int(message.text.strip())
    else:
        await message.answer(
            "Iltimos, xabarni forward qiling yoki faqat Telegram ID raqamini yuboring."
        )
        return

    if is_admin(target_id):
        await message.answer("Bu foydalanuvchi bosh admin - sotuvchi qila olmaysiz.", reply_markup=kb.sellers_menu())
        await state.clear()
        return

    if await db.is_owner(target_id):
        await message.answer(
            "Bu foydalanuvchi allaqachon bir do'konning egasi - sotuvchi qila olmaysiz.",
            reply_markup=kb.sellers_menu(),
        )
        await state.clear()
        return

    if await db.is_seller(target_id):
        await message.answer(
            "Bu foydalanuvchi allaqachon (sizning yoki boshqa) do'konga sotuvchi sifatida qo'shilgan.",
            reply_markup=kb.sellers_menu(),
        )
        await state.clear()
        return

    branch_id = await get_branch_id(shop_id)
    await db.add_seller(target_id, shop_id, full_name, username, added_by=message.from_user.id, branch_id=branch_id)
    await state.clear()

    name_part = f" ({full_name})" if full_name else ""
    branch_label = "Bosh filial"
    if branch_id:
        branch = await db.get_branch(shop_id, branch_id)
        if branch:
            branch_label = branch["name"]
    await message.answer(
        f"✅ Sotuvchi qo'shildi{name_part}. ID: {target_id}\n"
        f"🏢 Filial: {branch_label}\n\n"
        f"Endi u botga /start bosib kira oladi - lekin faqat savdo, mahsulotlar "
        f"ro'yxatini ko'rish (tannarxsiz) va qarz daftar bilan ishlay oladi. "
        f"Birinchi /start'da undan ismi va telefon raqami so'raladi - shu "
        f"ma'lumot \"📋 Sotuvchilar ro'yxati\"da ko'rinadi.",
        reply_markup=kb.sellers_menu(),
    )

    try:
        await message.bot.send_message(
            target_id,
            "✅ Sizga do'kon boshqaruv botidan sotuvchi sifatida foydalanish huquqi berildi.\n"
            "Boshlash uchun /start buyrug'ini bosing.",
        )
    except Exception:
        pass


@router.message(F.text == "📋 Sotuvchilar ro'yxati")
async def list_sellers(message: Message, state: FSMContext):
    await state.clear()
    shop_id = await _require_owner(message)
    if shop_id is None:
        return

    sellers = await db.get_sellers(shop_id)
    if not sellers:
        await message.answer("Hozircha sotuvchilar qo'shilmagan.", reply_markup=kb.sellers_menu())
        return

    await message.answer("🧑‍💼 <b>Sotuvchilar:</b>", parse_mode="HTML", reply_markup=kb.sellers_menu())
    for s in sellers:
        telegram_label = s["full_name"] or (f"@{s['username']}" if s["username"] else str(s["telegram_id"]))
        name_line = f"👤 {s['seller_name']}" if s.get("seller_name") else f"👤 {telegram_label}"
        phone_line = f"\n📞 {s['phone_number']}" if s.get("phone_number") else "\n📞 (hali kiritmagan)"

        branch_label = "Bosh filial"
        if s.get("branch_id"):
            branch = await db.get_branch(shop_id, s["branch_id"])
            if branch:
                branch_label = branch["name"]

        await message.answer(
            f"{name_line}{phone_line}\n🏢 Filial: {branch_label}\nTelegram: {telegram_label}\nID: {s['telegram_id']}",
            reply_markup=kb.seller_action_kb(s["telegram_id"]),
        )


@router.callback_query(F.data.startswith("seller_branch_menu_"))
async def seller_branch_menu_cb(callback: CallbackQuery):
    shop_id = callback.from_user.id
    if not await db.is_owner(shop_id):
        await callback.answer("Bu bo'lim faqat do'kon egasi uchun.", show_alert=True)
        return

    seller_telegram_id = int(callback.data.replace("seller_branch_menu_", ""))
    seller = await db.get_seller(seller_telegram_id)
    if not seller or seller.get("shop_id") != shop_id:
        await callback.answer("Sotuvchi topilmadi.", show_alert=True)
        return

    branches = await db.get_branches(shop_id)
    await callback.message.answer(
        "Sotuvchini qaysi filialga o'tkazishni tanlang:",
        reply_markup=kb.seller_branch_choice_kb(seller_telegram_id, branches, seller.get("branch_id")),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("seller_branch_set_"))
async def seller_branch_set_cb(callback: CallbackQuery):
    shop_id = callback.from_user.id
    if not await db.is_owner(shop_id):
        await callback.answer("Bu bo'lim faqat do'kon egasi uchun.", show_alert=True)
        return

    parts = callback.data.split("_")
    seller_telegram_id = int(parts[-2])
    branch_val = parts[-1]
    branch_id = None if branch_val == "0" else int(branch_val)

    # branch_id belgilangan bo'lsa, shu do'konga tegishli ekanini tekshiramiz -
    # boshqa do'kon egasining filial id'sini taxmin qilib yubormasin.
    if branch_id is not None:
        branch = await db.get_branch(shop_id, branch_id)
        if not branch:
            await callback.answer("Filial topilmadi.", show_alert=True)
            return
        branch_label = branch["name"]
    else:
        branch_label = "Bosh filial"

    moved = await db.set_seller_branch(shop_id, seller_telegram_id, branch_id)
    if not moved:
        await callback.answer("Sotuvchi topilmadi.", show_alert=True)
        return

    await callback.answer(f"✅ \"{branch_label}\" filialiga ko'chirildi.")
    try:
        await callback.message.edit_text(f"🏢 Sotuvchi endi: {branch_label}")
    except Exception:
        pass


@router.callback_query(F.data.startswith("remove_seller_"))
async def remove_seller_cb(callback: CallbackQuery):
    if not await db.is_owner(callback.from_user.id):
        await callback.answer()
        return

    target_id = int(callback.data.replace("remove_seller_", ""))
    removed = await db.remove_seller(callback.from_user.id, target_id)
    if removed:
        await callback.message.edit_text(f"❌ O'chirildi. ID: {target_id}")
    else:
        await callback.answer("Topilmadi (avval o'chirilgan bo'lishi mumkin).", show_alert=True)
    await callback.answer()
