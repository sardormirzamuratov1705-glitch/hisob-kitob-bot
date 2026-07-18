from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

import database as db
import keyboards as kb

router = Router()


class BranchManage(StatesGroup):
    new_name = State()


# MUHIM: bu bo'lim tugmasi faqat HAQIQIY do'kon egasiga ko'rsatiladi
# (handlers/start.py -> kb.main_menu), lekin har bir handler ichida ham
# db.is_owner() bilan qayta tekshiramiz - na bosh admin, na sotuvchi shu
# bo'limga boshqa yo'l bilan (masalan eski chatdan matnni qayta yuborib)
# kira olmasligi uchun.

async def _require_owner(message: Message):
    if not await db.is_owner(message.from_user.id):
        await message.answer("Bu bo'lim faqat do'kon egasi uchun.")
        return None
    return message.from_user.id  # owner uchun shop_id = o'z telegram_id'si


async def _require_owner_cb(callback: CallbackQuery):
    if not await db.is_owner(callback.from_user.id):
        await callback.answer("Bu bo'lim faqat do'kon egasi uchun.", show_alert=True)
        return None
    return callback.from_user.id


@router.message(F.text == "🏢 Filiallar")
async def branches_menu(message: Message, state: FSMContext):
    await state.clear()
    shop_id = await _require_owner(message)
    if shop_id is None:
        return
    branches = await db.get_branches(shop_id)
    if not branches:
        await message.answer(
            "Hozircha filial yo'q. Yangi filial qo'shishingiz mumkin:",
            reply_markup=kb.branch_manage_kb(branches),
        )
        return
    await message.answer(
        "Mavjud filiallar:",
        reply_markup=kb.branch_manage_kb(branches),
    )


@router.callback_query(F.data == "branch_manage_new")
async def branch_manage_new_cb(callback: CallbackQuery, state: FSMContext):
    shop_id = await _require_owner_cb(callback)
    if shop_id is None:
        return
    await state.set_state(BranchManage.new_name)
    await callback.message.answer("Yangi filial nomini kiriting:")
    await callback.answer()


@router.message(BranchManage.new_name)
async def branch_manage_new_name(message: Message, state: FSMContext):
    shop_id = await _require_owner(message)
    if shop_id is None:
        await state.clear()
        return
    name = message.text.strip()
    if not name:
        await message.answer("Filial nomi bo'sh bo'lishi mumkin emas. Qaytadan kiriting:")
        return
    await state.clear()
    branch = await db.add_branch(shop_id, name)
    branches = await db.get_branches(shop_id)
    await message.answer(
        f"✅ \"{branch['name']}\" filiali qo'shildi.",
        reply_markup=kb.branch_manage_kb(branches),
    )


@router.callback_query(F.data.startswith("branch_noop_"))
async def branch_noop_cb(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(F.data.startswith("branch_delete_"))
async def branch_delete_cb(callback: CallbackQuery):
    shop_id = await _require_owner_cb(callback)
    if shop_id is None:
        return
    branch_id = int(callback.data.split("_")[-1])
    deleted = await db.delete_branch(shop_id, branch_id)
    if not deleted:
        await callback.answer("Filial topilmadi", show_alert=True)
        return
    await callback.answer("Filial o'chirildi.", show_alert=True)
    branches = await db.get_branches(shop_id)
    try:
        await callback.message.edit_text(
            "Mavjud filiallar:" if branches else
            "Hozircha filial yo'q. Yangi filial qo'shishingiz mumkin:",
            reply_markup=kb.branch_manage_kb(branches),
        )
    except Exception:
        pass
