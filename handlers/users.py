from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

import config
import database as db
import keyboards as kb
from access_control import is_admin, check_subscription_access, subscription_status_emoji

router = Router()


class AddOwner(StatesGroup):
    waiting_input = State()


class ExtendSubscription(StatesGroup):
    waiting_custom_days = State()


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

    await callback.answer(f"✅ +{days} kun qo'shildi")
    await _refresh_owner_card(callback, target_id)

    try:
        await callback.message.bot.send_message(
            target_id,
            f"✅ Bosh admin obunangizni qo'lda {days} kunga uzaytirdi.\n"
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
        f"✏️ ID {target_id} uchun necha kunlik obuna qo'shmoqchisiz? Faqat son yuboring (masalan: 45)."
    )


@router.message(ExtendSubscription.waiting_custom_days)
async def extend_custom_finish(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()
    target_id = data.get("target_owner_id")
    text = (message.text or "").strip()

    if not text.lstrip("-").isdigit() or int(text) <= 0:
        await message.answer("Iltimos, musbat butun son yuboring (masalan: 45).")
        return

    days = int(text)
    await state.clear()

    new_until = await db.extend_owner_subscription(target_id, days)
    if new_until is None:
        await message.answer("Bu ega endi topilmadi.", reply_markup=kb.users_menu())
        return

    await message.answer(
        f"✅ ID {target_id} uchun {days} kun qo'shildi. Endi {new_until} sanagacha amal qiladi.",
        reply_markup=kb.users_menu(),
    )

    try:
        await message.bot.send_message(
            target_id,
            f"✅ Bosh admin obunangizni qo'lda {days} kunga uzaytirdi.\n"
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
