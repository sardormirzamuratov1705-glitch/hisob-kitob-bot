from aiogram.types import ReplyKeyboardMarkup, InlineKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder


def main_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="📦 Sklad")
    builder.button(text="💰 Kirim/Chiqim")
    builder.button(text="📒 Qarz daftar")
    builder.button(text="📊 Hisobot")
    builder.adjust(2, 2)
    return builder.as_markup(resize_keyboard=True)


def sklad_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="➕ Mahsulot qo'shish")
    builder.button(text="📋 Mahsulotlar ro'yxati")
    builder.button(text="⬅️ Orqaga")
    builder.adjust(1, 1, 1)
    return builder.as_markup(resize_keyboard=True)


def kirim_chiqim_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="➕ Kirim qo'shish")
    builder.button(text="➖ Chiqim qo'shish")
    builder.button(text="📈 Bugungi holat")
    builder.button(text="⬅️ Orqaga")
    builder.adjust(2, 1, 1)
    return builder.as_markup(resize_keyboard=True)


def qarz_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="➕ Qarz qo'shish")
    builder.button(text="📋 Qarzdorlar ro'yxati")
    builder.button(text="⬅️ Orqaga")
    builder.adjust(1, 1, 1)
    return builder.as_markup(resize_keyboard=True)


def hisobot_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="📊 Umumiy hisobot")
    builder.button(text="📥 Excel yuklab olish")
    builder.button(text="⬅️ Orqaga")
    builder.adjust(1, 1, 1)
    return builder.as_markup(resize_keyboard=True)


def skip_photo_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Rasmsiz davom etish", callback_data="skip_photo")
    return builder.as_markup()


def product_action_kb(product_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑 O'chirish", callback_data=f"del_product_{product_id}")
    return builder.as_markup()


def debt_action_kb(debt_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ To'landi", callback_data=f"pay_debt_{debt_id}")
    return builder.as_markup()
