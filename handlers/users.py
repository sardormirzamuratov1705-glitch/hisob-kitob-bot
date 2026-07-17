from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

import database as db
import keyboards as kb
from access_control import is_admin

router = Router()


class AddOwner(StatesGroup):
    waiting_input = State()


# MUHIM: bu bo'lim tugmasi faqat bosh adminga (config.ADMIN_IDS) ko'rsatiladi
# (handlers/start.py -> kb.main_menu), lekin har bir handler ichida ham
# is_admin() bilan qayta tekshiramiz - do'kon egasi boshqa yo'l bilan (masalan,
# eski chatdan matnni qayta yuborib) shu bo'limga kira olmasligi uchun.

@router.message(F.text == "👥 Foydalanuvchilar")
async def open_users(message: Message, state: FSMContext):
    await state.clear()
    if not is_admin(message.from_user.id):
        return
    await message.answer("Foydalanuvchilar bo'limi:", reply_markup=kb.users_menu())


@router.message(F.text == "➕ Do'kon egasi qo'shish")
async def add_owner_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.set_state(AddOwner.waiting_input)
    await message.answer(
        "Yangi do'kon egasini qo'shish uchun:\n\n"
        "• uning istalgan xabarini shu yerga forward qiling,\n"
        "yoki\n"
        "• uning Telegram ID raqamini yuboring (masalan, @userinfobot orqali bilib olishi mumkin)."
    )


@router.message(AddOwner.waiting_input)
async def add_owner_finish(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
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
        await message.answer("Bu foydalanuvchi allaqachon bosh admin.", reply_markup=kb.users_menu())
        await state.clear()
        return

    if await db.is_owner(target_id):
        await message.answer(
            "Bu foydalanuvchi allaqachon do'kon egasi sifatida qo'shilgan.",
            reply_markup=kb.users_menu(),
        )
        await state.clear()
        return

    await db.add_owner(target_id, full_name, username, added_by=message.from_user.id)
    await state.clear()

    name_part = f" ({full_name})" if full_name else ""
    await message.answer(
        f"✅ Do'kon egasi qo'shildi{name_part}. ID: {target_id}\n\n"
        f"Endi u botga /start bosib to'liq kira oladi (lekin foydalanuvchi "
        f"qo'sha/o'chira olmaydi).",
        reply_markup=kb.users_menu(),
    )

    try:
        await message.bot.send_message(
            target_id,
            "✅ Sizga do'kon boshqaruv botidan foydalanish huquqi berildi.\n"
            "Boshlash uchun /start buyrug'ini bosing.",
        )
    except Exception:
        pass


@router.message(F.text == "📋 Do'kon egalari ro'yxati")
async def list_owners(message: Message, state: FSMContext):
    await state.clear()
    if not is_admin(message.from_user.id):
        return

    owners = await db.get_owners()
    if not owners:
        await message.answer("Hozircha do'kon egalari qo'shilmagan.", reply_markup=kb.users_menu())
        return

    await message.answer("👥 <b>Do'kon egalari:</b>", parse_mode="HTML", reply_markup=kb.users_menu())
    for o in owners:
        label = o["full_name"] or (f"@{o['username']}" if o["username"] else str(o["telegram_id"]))
        await message.answer(
            f"👤 {label}\nID: {o['telegram_id']}",
            reply_markup=kb.owner_action_kb(o["telegram_id"]),
        )


@router.callback_query(F.data.startswith("remove_owner_"))
async def remove_owner_cb(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return

    target_id = int(callback.data.replace("remove_owner_", ""))
    removed = await db.remove_owner(target_id)
    if removed:
        await callback.message.edit_text(f"❌ O'chirildi. ID: {target_id}")
    else:
        await callback.answer("Topilmadi (avval o'chirilgan bo'lishi mumkin).", show_alert=True)
    await callback.answer()
