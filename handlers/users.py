from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config
import database as db
import keyboards as kb
import access_control
from access_control import is_admin, check_subscription_access, subscription_status_emoji, register_extra_admin
from handlers.products import ExcelFill, send_products_excel_template

router = Router()


class AddOwner(StatesGroup):
    waiting_input = State()


class AddAdmin(StatesGroup):
    waiting_input = State()


class ExtendSubscription(StatesGroup):
    waiting_custom_days = State()


class EditPaymentSetting(StatesGroup):
    waiting_value = State()


class Broadcast(StatesGroup):
    waiting_text = State()


# 10-BOSQICH: "⚙️ To'lov sozlamalari" bo'limida tahrirlanadigan kalitlar va
# ularning odam o'qiydigan nomlari. PRICE_SETTING_KEYS - shu kalitlar uchun
# kiritilgan qiymat albatta musbat butun son bo'lishi tekshiriladi (so'm).
SETTING_LABELS = {
    "price_1m": "1 oylik obuna narxi",
    "price_3m": "3 oylik obuna narxi",
    "price_12m": "12 oylik obuna narxi",
    "card_number": "Karta raqami",
    "card_holder": "Karta egasi (F.I.Sh.)",
    "click_number": "Click raqami",
    "payme_number": "Payme raqami",
}
PRICE_SETTING_KEYS = {"price_1m", "price_3m", "price_12m"}


async def _payment_settings_text() -> str:
    plans = await db.get_subscription_plans()
    requisites = await db.get_payment_requisites()
    price_1m = f"{plans['1m']['price']:,}".replace(",", " ")
    price_3m = f"{plans['3m']['price']:,}".replace(",", " ")
    price_12m = f"{plans['12m']['price']:,}".replace(",", " ")
    return (
        "⚙️ <b>To'lov sozlamalari</b>\n\n"
        f"📦 1 oy: {price_1m} so'm\n"
        f"📦 3 oy: {price_3m} so'm\n"
        f"📦 12 oy: {price_12m} so'm\n\n"
        f"💳 Karta: <code>{requisites['card_number']}</code> ({requisites['card_holder']})\n"
        f"🔵 Click: {requisites['click_number']}\n"
        f"🟢 Payme: {requisites['payme_number']}\n\n"
        "O'zgartirish uchun quyidagilardan birini tanlang:"
    )


def _owner_card_text(o: dict, access: dict | None) -> str:
    """9-BOSQICH: ro'yxatdagi va uzaytirish/bloklash amalidan keyin qayta
    chizib bo'lmaydigan (chunki tugmalar o'chib qoladi) kartochka matni -
    ega ma'lumotlari + obuna holati belgisi (✅/⏳/⛔)."""
    telegram_label = o["full_name"] or (f"@{o['username']}" if o["username"] else str(o["telegram_id"]))
    name_line = f"👤 {o['owner_name']}" if o.get("owner_name") else f"👤 {telegram_label}"
    shop_line = f"\n🏪 {o['shop_name']}" if o.get("shop_name") else "\n🏪 (hali kiritmagan)"
    phone_line = f"\n📞 {o['phone_number']}" if o.get("phone_number") else "\n📞 (hali kiritmagan)"

    emoji = subscription_status_emoji(access)
    if access and access.get("status") == "blocked":
        sub_line = "\n⛔ Majburiy bloklangan"
    elif access and access.get("status") == "pending_trial":
        sub_line = f"\n{emoji} Sinov muddati hali tasdiqlanmagan"
    elif access and access.get("days_left") is not None:
        days_left = access["days_left"]
        if days_left >= 0:
            sub_line = f"\n{emoji} Obuna: {days_left} kun qoldi ({access['status']})"
        else:
            sub_line = f"\n{emoji} Obuna tugagan ({-days_left} kun oldin)"
    else:
        sub_line = f"\n{emoji} Obuna holati noma'lum"

    return (
        f"{name_line}{shop_line}{phone_line}\nTelegram: {telegram_label}\n"
        f"ID: {o['telegram_id']}{sub_line}"
    )


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


# ---------- BIR MARTALIK TAKLIF LINKI ----------
# Agar do'kon egasining Telegram ID'sini bilmasangiz yoki undan xabar forward
# qila olmasangiz - shu link orqali ham qo'shish mumkin. Link FAQAT BITTA
# marta, FAQAT BITTA odam tomonidan ishlatiladi: kimdir link orqali botni
# ochib do'kon egasi bo'lib qolgach, o'sha link boshqa hech kim uchun
# ishlamay qoladi (garchi u qayta bosilsa ham).

@router.message(F.text == "🔗 Bir martalik link")
async def create_invite_link(message: Message):
    if not is_admin(message.from_user.id):
        return

    token = await db.create_owner_invite(message.from_user.id)
    me = await message.bot.get_me()
    link = f"https://t.me/{me.username}?start=owner_{token}"

    await message.answer(
        "🔗 Bir martalik taklif linki tayyor:\n\n"
        f"{link}\n\n"
        "Buni yangi do'kon egasiga yuboring. U linkni bosib botni ochishi bilanoq "
        "avtomatik do'kon egasi sifatida qo'shiladi.\n\n"
        "⚠️ Link faqat BITTA marta ishlaydi — birinchi bosgan odam uchun. "
        "Agar boshqa birov ham shu linkni keyinroq bossa, unga \"link band\" "
        "deb xabar beriladi.",
        reply_markup=kb.users_menu(),
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
        f"qo'sha/o'chira olmaydi). Birinchi /start'da undan ismi va do'koni "
        f"nomi/turi so'raladi - shu ma'lumot \"📋 Do'kon egalari ro'yxati\"da "
        f"ko'rinadi.",
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


# ---------- YANGI BOSH ADMIN QO'SHISH ----------
# Do'kon egasi qo'shishdagi bilan bir xil naqsh (forward/ID yoki bir martalik
# havola), FAQAT natijada odam do'kon egasi emas, BOSH ADMIN bo'ladi - ya'ni
# u ham "Foydalanuvchilar" bo'limiga kirib, boshqa do'kon egalari/adminlarni
# boshqara oladi. Shuning uchun bu amalni FAQAT mavjud bosh admin qila oladi
# va juda ehtiyotkorlik bilan ishlatilishi kerak.

@router.message(F.text == "👑 Admin qo'shish")
async def add_admin_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.set_state(AddAdmin.waiting_input)
    await message.answer(
        "⚠️ Yangi BOSH ADMIN qo'shmoqchisiz - u sizga teng huquqqa ega bo'ladi "
        "(barcha do'kon egalarini, adminlarni ko'radi/boshqaradi).\n\n"
        "Qo'shish uchun:\n\n"
        "• uning istalgan xabarini shu yerga forward qiling,\n"
        "yoki\n"
        "• uning Telegram ID raqamini yuboring."
    )


@router.message(F.text == "🔗 Bir martalik admin havolasi")
async def create_admin_invite_link(message: Message):
    if not is_admin(message.from_user.id):
        return

    token = await db.create_admin_invite(message.from_user.id)
    me = await message.bot.get_me()
    link = f"https://t.me/{me.username}?start=admin_{token}"

    await message.answer(
        "🔗 Bir martalik ADMIN taklif linki tayyor:\n\n"
        f"{link}\n\n"
        "⚠️ Buni FAQAT ishonchli odamga yuboring - link orqali botni ochgan "
        "kishi darhol sizga TENG bosh admin huquqiga ega bo'ladi.\n\n"
        "Link faqat BITTA marta ishlaydi — birinchi bosgan odam uchun.",
        reply_markup=kb.users_menu(),
    )


@router.message(AddAdmin.waiting_input)
async def add_admin_finish(message: Message, state: FSMContext):
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
            "Iltimos, xabarni forward qiling yoki faqat Telegram ID raqamini yuboring.\n\n"
            "Eslatma: agar foydalanuvchi Telegram sozlamalarida \"forward qilinganda "
            "hisobim ko'rsatilmasin\" degan maxfiylik sozlamasini yoqqan bo'lsa, "
            "forward orqali ID aniqlanmaydi - bunday holda uning ID raqamini "
            "(masalan @userinfobot orqali) so'rab, shu yerga to'g'ridan-to'g'ri yuboring."
        )
        return

    if is_admin(target_id):
        await message.answer("Bu foydalanuvchi allaqachon bosh admin.", reply_markup=kb.users_menu())
        await state.clear()
        return

    if await db.is_owner(target_id):
        await message.answer(
            "Bu foydalanuvchi do'kon egasi sifatida ro'yxatdan o'tgan - avval uni "
            "\"📋 Do'kon egalari ro'yxati\"dan o'chiring, keyin admin sifatida qo'shing.",
            reply_markup=kb.users_menu(),
        )
        await state.clear()
        return

    if await db.is_seller(target_id):
        await message.answer(
            "Bu foydalanuvchi biror do'konga sotuvchi sifatida ulangan - avval uni "
            "o'sha do'kon egasi sotuvchilar ro'yxatidan o'chirishi kerak.",
            reply_markup=kb.users_menu(),
        )
        await state.clear()
        return

    await db.add_admin(target_id, full_name, username, added_by=message.from_user.id)
    register_extra_admin(target_id)
    await state.clear()

    name_part = f" ({full_name})" if full_name else ""
    await message.answer(
        f"✅ Yangi bosh admin qo'shildi{name_part}. ID: {target_id}\n\n"
        "U hozirdanoq to'liq admin huquqiga ega (botni qayta ishga tushirish shart emas).",
        reply_markup=kb.users_menu(),
    )

    try:
        await message.bot.send_message(
            target_id,
            "👑 Sizga botda BOSH ADMIN huquqi berildi.\n"
            "Boshlash uchun /start buyrug'ini bosing.",
        )
    except Exception:
        pass


@router.message(F.text == "👑 Adminlar ro'yxati")
async def list_admins(message: Message, state: FSMContext):
    await state.clear()
    if not is_admin(message.from_user.id):
        return

    lines = ["👑 <b>Bosh adminlar</b>\n"]
    if config.ADMIN_IDS:
        lines.append("<b>.env orqali (o'chirib bo'lmaydi):</b>")
        for admin_id in config.ADMIN_IDS:
            lines.append(f"• {admin_id}")

    db_admins = await db.get_admins()
    if db_admins:
        lines.append("\n<b>Botdan qo'shilganlar:</b>")

    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=kb.users_menu())

    for a in db_admins:
        label = a["full_name"] or (f"@{a['username']}" if a["username"] else str(a["telegram_id"]))
        await message.answer(
            f"👤 {label}\nID: {a['telegram_id']}",
            reply_markup=kb.admin_action_kb(a["telegram_id"]),
        )


@router.callback_query(F.data.startswith("remove_admin_"))
async def remove_admin_cb(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return

    target_id = int(callback.data.replace("remove_admin_", ""))
    if target_id == callback.from_user.id:
        await callback.answer("O'zingizni o'chira olmaysiz.", show_alert=True)
        return

    removed = await db.remove_admin(target_id)
    if removed:
        access_control._extra_admin_ids.discard(target_id)
        await callback.message.edit_text(f"❌ Admin huquqi olib tashlandi. ID: {target_id}")
    else:
        await callback.answer(
            "Topilmadi (bu odam .env orqali qo'shilgan bo'lishi mumkin - "
            "u faqat .env orqali olib tashlanadi).",
            show_alert=True,
        )
    await callback.answer()


@router.message(F.text == "📋 Do'kon egalari ro'yxati")
async def list_owners(message: Message, state: FSMContext):
    await state.clear()
    if not is_admin(message.from_user.id):
        return

    owners = await db.get_owners()
    if not owners:
        await message.answer("Hozircha do'kon egalari qo'shilmagan.", reply_markup=kb.users_menu())
        return

    await message.answer(
        "👥 <b>Do'kon egalari</b> (✅ - joyida, ⏳ - diqqat talab qiladi, ⛔ - kirish yopiq):",
        parse_mode="HTML",
        reply_markup=kb.users_menu(),
    )
    for o in owners:
        access = await check_subscription_access(o["telegram_id"])
        blocked = bool(access and access.get("status") == "blocked")
        await message.answer(
            _owner_card_text(o, access),
            reply_markup=kb.owner_action_kb(o["telegram_id"], blocked=blocked),
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


# ---------- 9-BOSQICH: ADMIN PANELIDAN OBUNANI QO'LDA BOSHQARISH ----------
# "📋 Do'kon egalari ro'yxati"dagi har bir kartochka ostida uchta amal:
# obunani qo'lda uzaytirish (to'lov chekisiz), majburiy bloklash/blokdan
# chiqarish va o'chirish (yuqorida, eski handler).

async def _refresh_owner_card(callback: CallbackQuery, target_id: int):
    """Amaldan (uzaytirish/bloklash) keyin kartochka matni va tugmalarini
    yangi holatga mos qilib qayta chizadi."""
    owner = await db.get_owner(target_id)
    if not owner:
        await callback.message.edit_text(f"❌ Bu ega endi topilmadi (o'chirilgan bo'lishi mumkin). ID: {target_id}")
        return
    access = await check_subscription_access(target_id)
    blocked = bool(access and access.get("status") == "blocked")
    await callback.message.edit_text(
        _owner_card_text(owner, access),
        reply_markup=kb.owner_action_kb(target_id, blocked=blocked),
    )


@router.callback_query(F.data.startswith("extend_menu:"))
async def extend_menu_cb(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    target_id = int(callback.data.split(":", 1)[1])
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=kb.extend_subscription_kb(target_id))


@router.callback_query(F.data.startswith("extend_back:"))
async def extend_back_cb(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    target_id = int(callback.data.split(":", 1)[1])
    await callback.answer()
    await _refresh_owner_card(callback, target_id)


@router.callback_query(F.data.startswith("extend_days:"))
async def extend_days_cb(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return

    _, target_id_raw, days_raw = callback.data.split(":", 2)
    target_id = int(target_id_raw)
    days = int(days_raw)

    new_until = await db.extend_owner_subscription(target_id, days)
    if new_until is None:
        await callback.answer("Bu ega endi topilmadi.", show_alert=True)
        return

    if days >= 0:
        await callback.answer(f"✅ +{days} kun qo'shildi")
        owner_note = f"✅ Bosh admin obunangizni qo'lda {days} kunga uzaytirdi."
    else:
        await callback.answer(f"✅ {abs(days)} kun ayirildi")
        owner_note = f"⚠️ Bosh admin obunangizni qo'lda {abs(days)} kunga qisqartirdi."
    await _refresh_owner_card(callback, target_id)

    try:
        await callback.message.bot.send_message(
            target_id,
            f"{owner_note}\n"
            f"📅 Endi {new_until} sanagacha amal qiladi.",
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("extend_custom:"))
async def extend_custom_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    target_id = int(callback.data.split(":", 1)[1])
    await callback.answer()
    await state.set_state(ExtendSubscription.waiting_custom_days)
    await state.update_data(target_owner_id=target_id)
    await callback.message.answer(
        f"✏️ ID {target_id} uchun necha kunlik obuna qo'shmoqchisiz? Son yuboring "
        f"(masalan: 45), xato qo'shib qo'ygan bo'lsangiz tuzatish uchun manfiy son ham "
        f"yuborishingiz mumkin (masalan: -10)."
    )


@router.message(ExtendSubscription.waiting_custom_days)
async def extend_custom_finish(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()
    target_id = data.get("target_owner_id")
    text = (message.text or "").strip()

    try:
        days = int(text)
    except ValueError:
        days = None
    if days is None or days == 0:
        await message.answer(
            "Iltimos, butun son yuboring (masalan: 45), yoki kamaytirish uchun "
            "manfiy son yuboring (masalan: -10)."
        )
        return

    await state.clear()

    new_until = await db.extend_owner_subscription(target_id, days)
    if new_until is None:
        await message.answer("Bu ega endi topilmadi.", reply_markup=kb.users_menu())
        return

    if days >= 0:
        await message.answer(
            f"✅ ID {target_id} uchun {days} kun qo'shildi. Endi {new_until} sanagacha amal qiladi.",
            reply_markup=kb.users_menu(),
        )
        owner_note = f"✅ Bosh admin obunangizni qo'lda {days} kunga uzaytirdi."
    else:
        await message.answer(
            f"✅ ID {target_id} uchun {abs(days)} kun ayirildi. Endi {new_until} sanagacha amal qiladi.",
            reply_markup=kb.users_menu(),
        )
        owner_note = f"⚠️ Bosh admin obunangizni qo'lda {abs(days)} kunga qisqartirdi."

    try:
        await message.bot.send_message(
            target_id,
            f"{owner_note}\n"
            f"📅 Endi {new_until} sanagacha amal qiladi.",
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("block_owner:"))
async def block_owner_cb(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    target_id = int(callback.data.split(":", 1)[1])
    ok = await db.set_owner_blocked(target_id, True)
    if not ok:
        await callback.answer("Bu ega endi topilmadi.", show_alert=True)
        return

    await callback.answer("🚫 Bloklandi")
    await _refresh_owner_card(callback, target_id)

    try:
        await callback.message.bot.send_message(
            target_id,
            "⛔ Bosh admin sizning obunangizni majburan bloklandi. "
            "Savolingiz bo'lsa, bosh admin bilan bog'laning.",
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("unblock_owner:"))
async def unblock_owner_cb(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    target_id = int(callback.data.split(":", 1)[1])
    ok = await db.set_owner_blocked(target_id, False)
    if not ok:
        await callback.answer("Bu ega endi topilmadi.", show_alert=True)
        return

    await callback.answer("✅ Blokdan chiqarildi")
    await _refresh_owner_card(callback, target_id)

    try:
        await callback.message.bot.send_message(
            target_id,
            "✅ Bosh admin sizning blokingizni bekor qildi. Obunangiz oldingi holatiga qaytdi.",
        )
    except Exception:
        pass


# ---------- ADMIN: BOSHQA DO'KONNING SKLADINI EXCEL BILAN TO'LDIRISH ----------
# handlers/products.py'dagi ExcelFill holati va shablon/qayta ishlash
# funksiyalari shu yerda qayta ishlatiladi (bitta Dispatcher'ga barcha
# routerlar ulangani uchun state global) - faqat target_shop_id bu yerda
# bosilgan kartochkadagi eganing telegram_id'siga (= uning shop_id'siga)
# o'rnatiladi, admin o'zining shop_id'siga emas (uning umuman do'koni yo'q).

@router.callback_query(F.data.startswith("admin_sklad_excel:"))
async def admin_sklad_excel_start_cb(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    target_id = int(callback.data.split(":", 1)[1])
    owner = await db.get_owner(target_id)
    if not owner:
        await callback.answer("Bu ega endi topilmadi.", show_alert=True)
        return

    await callback.answer()
    await state.update_data(target_shop_id=target_id)
    await state.set_state(ExcelFill.waiting_file)
    await callback.message.answer(f"🏪 Do'kon egasi: <b>{owner.get('full_name') or target_id}</b>", parse_mode="HTML")
    await send_products_excel_template(callback.message)


# ---------- 9-BOSQICH: KUTILAYOTGAN TO'LOVLAR RO'YXATI ----------
# handlers/subscription.py'dagi pay_approve:/pay_reject: callback'lari
# (7-bosqichda yozilgan) shu yerdan chiqadigan xabarlar uchun ham ishlaydi -
# ular chekni kim yuborganidan (owner o'zi yuborganmi, shu yerdan qayta
# ko'rsatilganmi) qat'i nazar bir xil ishlaydi.

@router.message(F.text == "💳 Kutilayotgan to'lovlar")
async def list_pending_payments(message: Message, state: FSMContext):
    await state.clear()
    if not is_admin(message.from_user.id):
        return

    payments = await db.get_pending_payments()
    if not payments:
        await message.answer("Hozircha kutilayotgan to'lovlar yo'q.", reply_markup=kb.users_menu())
        return

    await message.answer(
        f"💳 <b>Kutilayotgan to'lovlar</b> ({len(payments)} ta):",
        parse_mode="HTML",
        reply_markup=kb.users_menu(),
    )
    for p in payments:
        owner = await db.get_owner(p["owner_id"])
        owner_label = (owner or {}).get("shop_name") or (owner or {}).get("owner_name") \
            or (owner or {}).get("full_name") or str(p["owner_id"])
        plan = config.SUBSCRIPTION_PLANS.get(p.get("plan"), {})
        plan_label = plan.get("label", p.get("plan") or "erkin")
        price_text = f"{p['amount']:,.0f}".replace(",", " ")
        caption = (
            f"💳 <b>To'lov #{p['id']}</b>\n\n"
            f"🏪 {owner_label} (ID: {p['owner_id']})\n"
            f"📦 Tarif: {plan_label} — {price_text} so'm ({p.get('days') or 0} kun)\n"
            f"🕓 Yuborilgan: {p['created_at']}\n\n"
            "Chekni tekshirib, tasdiqlang yoki rad eting:"
        )
        if p.get("screenshot_file_id"):
            await message.answer_photo(
                p["screenshot_file_id"],
                caption=caption,
                reply_markup=kb.payment_decision_kb(p["id"]),
            )
        else:
            await message.answer(caption, reply_markup=kb.payment_decision_kb(p["id"]))


# ---------- 10-BOSQICH: OBUNA NARXLARI VA TO'LOV REKVIZITLARINI TAHRIRLASH ----------
# Ilgari SUBSCRIPTION_PRICE_* va PAYMENT_CARD_NUMBER/... faqat .env orqali
# o'zgartirilar edi (redeploy talab qilardi). Endi bosh admin buni
# to'g'ridan-to'g'ri bot ichidan, redeploy'siz o'zgartira oladi - qiymatlar
# "settings" jadvalida saqlanadi (database.get_setting/set_setting).

@router.message(F.text == "⚙️ To'lov sozlamalari")
async def open_payment_settings(message: Message, state: FSMContext):
    await state.clear()
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        await _payment_settings_text(),
        parse_mode="HTML",
        reply_markup=kb.payment_settings_kb(),
    )


@router.callback_query(F.data.startswith("editset:"))
async def edit_setting_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return

    key = callback.data.split(":", 1)[1]
    label = SETTING_LABELS.get(key)
    if not label:
        await callback.answer()
        return

    await callback.answer()
    await state.set_state(EditPaymentSetting.waiting_value)
    await state.update_data(setting_key=key)

    if key in PRICE_SETTING_KEYS:
        hint = "faqat son kiriting, masalan: 60000"
    else:
        hint = "matn kiriting"
    await callback.message.answer(f"✏️ Yangi <b>{label}</b> qiymatini kiriting ({hint}).", parse_mode="HTML")


@router.message(EditPaymentSetting.waiting_value)
async def edit_setting_finish(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()
    key = data.get("setting_key")
    label = SETTING_LABELS.get(key, key)
    text = (message.text or "").strip()

    if key in PRICE_SETTING_KEYS:
        if not text.isdigit() or int(text) <= 0:
            await message.answer("Iltimos, musbat butun son yuboring (masalan: 60000).")
            return
        value = str(int(text))
        display_value = f"{int(text):,}".replace(",", " ") + " so'm"
    else:
        if not text:
            await message.answer("Iltimos, matn yuboring.")
            return
        value = text
        display_value = text

    await db.set_setting(key, value)
    await state.clear()

    await message.answer(f"✅ {label} yangilandi: {display_value}")
    await message.answer(
        await _payment_settings_text(),
        parse_mode="HTML",
        reply_markup=kb.payment_settings_kb(),
    )


# ---------- UMUMIY E'LON (BROADCAST) ----------
# Bosh admin BARCHA do'kon egalari va sotuvchilarga bir vaqtda xabar
# yuborishi uchun (masalan yangi funksiya haqida e'lon).

@router.message(F.text == "📢 E'lon yuborish")
async def broadcast_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.set_state(Broadcast.waiting_text)
    await message.answer(
        "Barcha do'kon egalari va sotuvchilarga yuboriladigan xabar matnini yozing:"
    )


@router.message(Broadcast.waiting_text)
async def broadcast_preview(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    if not message.text:
        await message.answer("Iltimos, matn ko'rinishida yozing.")
        return

    await state.update_data(text=message.text)
    owners = await db.get_owners()
    sellers = await db.get_all_sellers()
    total = len(owners) + len(sellers)

    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Yuborish", callback_data="broadcast_send")
    builder.button(text="❌ Bekor qilish", callback_data="broadcast_cancel")
    builder.adjust(2)
    await message.answer(
        f"📢 <b>Xabar shu ko'rinishda yuboriladi:</b>\n\n{message.text}\n\n"
        f"👥 Qabul qiluvchilar: {total} ta ({len(owners)} do'kon egasi, {len(sellers)} sotuvchi)\n\n"
        f"Yuborishni tasdiqlaysizmi?",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data == "broadcast_cancel")
async def broadcast_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer("Bekor qilindi")
    await callback.message.edit_text("❌ E'lon yuborish bekor qilindi.")


@router.callback_query(F.data == "broadcast_send")
async def broadcast_send(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Bu bo'lim faqat bosh adminlar uchun.", show_alert=True)
        return

    data = await state.get_data()
    text = data.get("text")
    await state.clear()
    if not text:
        await callback.answer()
        await callback.message.edit_text("Xabar topilmadi, qaytadan urinib ko'ring.")
        return

    await callback.answer("Yuborilmoqda...")

    owners = await db.get_owners()
    sellers = await db.get_all_sellers()
    recipient_ids = {o["telegram_id"] for o in owners} | {s["telegram_id"] for s in sellers}

    sent, failed = 0, 0
    for telegram_id in recipient_ids:
        try:
            await callback.bot.send_message(telegram_id, f"📢 <b>E'lon</b>\n\n{text}", parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1

    await callback.message.edit_text(
        f"✅ E'lon yuborildi.\n\nYetkazildi: {sent} ta\nYetkazilmadi: {failed} ta"
    )
