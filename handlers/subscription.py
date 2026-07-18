import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

import config
import database as db
import keyboards as kb
from access_control import is_admin, is_owner_level, PaymentFlow

router = Router()


# ---------- O'ZI RO'YXATDAN O'TGANLAR UCHUN: SINOV MUDDATINI TASDIQLASH ----------
# handlers/start.py'dagi self_register_start endi trialni avtomatik
# boshlamaydi - yangi ega "pending_trial" holatida qoladi va shu yerdagi
# approve_trial:/reject_trial: callback'lari orqali bosh admin uni ko'rib
# chiqadi. "✅ Tasdiqlash" bosilganda admin necha kunlik sinov muddati
# berishni matn ko'rinishida (erkin son) kiritadi - shu holat FSM orqali
# kuzatiladi (bir vaqtning o'zida bir nechta so'rov kelsa ham chalkashmasin
# deb, target_owner_id va tahrirlanadigan xabar state'da saqlanadi).
class ApproveTrial(StatesGroup):
    waiting_days = State()


# ---------- 6-BOSQICH: TARIFLAR VA TO'LOV OYNASI ----------
# Bu bo'limga ikki yo'l bilan kirish mumkin:
#   1) Do'kon egasi o'zi asosiy menyudagi "💳 Obuna" tugmasini bossa
#      (obunasi hali tugamagan bo'lsa ham - muddatidan oldin uzaytirish
#      uchun ham foydali).
#   2) access_control.py'dagi bloklash ekranidagi "💳 Obunani uzaytirish"
#      tugmasi bosilsa (obuna trial+grace bilan tugagan bo'lsa).
#
# Ikkala holatda ham xuddi shu tariflar ro'yxati ko'rsatiladi.

TARIFFS_TEXT = (
    "💳 <b>Obuna tariflari</b>\n\n"
    "Quyidagi tariflardan birini tanlang - 3 va 12 oylik tariflarda "
    "chegirma mavjud:"
)


async def _show_tariffs(message: Message):
    plans = await db.get_subscription_plans()
    await message.answer(TARIFFS_TEXT, reply_markup=kb.subscription_plans_menu(plans))


@router.message(F.text == "💳 Obuna")
async def open_subscription_menu(message: Message, state: FSMContext):
    await state.clear()
    # Faqat HAQIQIY do'kon egasi uchun - sotuvchi va bosh adminda bu tugma
    # umuman ko'rsatilmaydi, lekin ikki karra himoya sifatida bu yerda ham
    # tekshiramiz (masalan eski chatdan matnni qayta yuborsa).
    if is_admin(message.from_user.id):
        return
    if not await is_owner_level(message.from_user.id):
        await message.answer(
            "Obunani faqat do'kon egasining o'zi uzaytira oladi. "
            "Iltimos, shu masalada do'kon egangizga murojaat qiling."
        )
        return
    await _show_tariffs(message)


@router.callback_query(F.data == "extend_subscription")
async def extend_subscription_entry(callback: CallbackQuery, state: FSMContext):
    """Bloklash ekranidagi (access_control.py) tugma. Sotuvchi ham bosishi
    mumkin (obunasi ega orqali bloklangani uchun), lekin to'lovni faqat
    ega amalga oshira olishi kerak."""
    await callback.answer()
    await state.clear()

    if is_admin(callback.from_user.id):
        return
    if not await is_owner_level(callback.from_user.id):
        await callback.message.answer(
            "Obunani faqat do'kon egasining o'zi uzaytira oladi. "
            "Iltimos, shu masalada do'kon egangizga murojaat qiling."
        )
        return
    await _show_tariffs(callback.message)


@router.callback_query(F.data.startswith("sub_plan:"))
async def choose_subscription_plan(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    if not await is_owner_level(callback.from_user.id):
        # Ehtiyot chorasi - oddiy holatda sotuvchi bu tugmani hech qachon
        # ko'rmaydi, chunki _show_tariffs unga chaqirilmaydi.
        return

    plan_key = callback.data.split(":", 1)[1]
    plans = await db.get_subscription_plans()
    plan = plans.get(plan_key)
    if not plan:
        await callback.message.answer("❌ Bu tarif topilmadi. Qaytadan urinib ko'ring: /start")
        return

    # 7-bosqich: chek skrinshotini kutamiz. Tanlangan tarif va HOZIRGI narx
    # (10-bosqich - admin narxni keyin o'zgartirsa ham, shu foydalanuvchi
    # tanlagan/ko'rgan narxdan to'laydi) state orqali receipt_received'ga
    # o'tkaziladi.
    await state.set_state(PaymentFlow.waiting_receipt)
    await state.update_data(
        subscription_plan=plan_key,
        plan_price=plan["price"],
        plan_days=plan["days"],
        plan_label=plan["label"],
    )

    requisites = await db.get_payment_requisites()
    price_text = f"{plan['price']:,}".replace(",", " ")
    text = (
        f"✅ Siz <b>{plan['label']}</b> tarifini tanladingiz — {price_text} so'm.\n\n"
        "💳 To'lov rekvizitlari:\n"
        f"• Karta: <code>{requisites['card_number']}</code> ({requisites['card_holder']})\n"
        f"• Click: {requisites['click_number']}\n"
        f"• Payme: {requisites['payme_number']}\n\n"
        "To'lovni amalga oshirgach, chek/skrinshotni shu yerga rasm qilib yuboring - "
        "u bosh adminga tekshirish uchun boradi va tasdiqlangach obunangiz "
        "avtomatik uzaytiriladi."
    )
    await callback.message.answer(text)


# ---------- 7-BOSQICH: CHEKNI QABUL QILISH VA ADMINGA YUBORISH ----------

@router.message(PaymentFlow.waiting_receipt, F.photo)
async def receipt_received(message: Message, state: FSMContext):
    data = await state.get_data()
    plan_key = data.get("subscription_plan")
    plan_price = data.get("plan_price")
    plan_days = data.get("plan_days")
    plan_label = data.get("plan_label")
    await state.clear()

    if not plan_key or plan_price is None or plan_days is None:
        await message.answer("❌ Tarif topilmadi, iltimos qaytadan boshlang: /start")
        return

    screenshot_file_id = message.photo[-1].file_id
    payment_id = await db.create_payment(
        owner_id=message.from_user.id,
        amount=plan_price,
        plan=plan_key,
        days=plan_days,
        screenshot_file_id=screenshot_file_id,
    )

    owner = await db.get_owner(message.from_user.id)
    owner_label = (owner or {}).get("shop_name") or (owner or {}).get("owner_name") \
        or message.from_user.full_name or str(message.from_user.id)
    price_text = f"{plan_price:,}".replace(",", " ")
    admin_caption = (
        f"💳 <b>Yangi to'lov (#{payment_id})</b>\n\n"
        f"🏪 {owner_label} (ID: {message.from_user.id})\n"
        f"📦 Tarif: {plan_label} — {price_text} so'm ({plan_days} kun)\n\n"
        "Chekni tekshirib, tasdiqlang yoki rad eting:"
    )
    sent_to_any_admin = False
    for admin_id in config.ADMIN_IDS:
        try:
            await message.bot.send_photo(
                admin_id,
                photo=screenshot_file_id,
                caption=admin_caption,
                reply_markup=kb.payment_decision_kb(payment_id),
            )
            sent_to_any_admin = True
        except Exception as e:
            logging.warning(f"Adminga ({admin_id}) chek yuborib bo'lmadi: {e}")

    if sent_to_any_admin:
        await message.answer(
            "✅ Chekingiz qabul qilindi va bosh adminga yuborildi.\n"
            "Tasdiqlangach obunangiz avtomatik uzaytiriladi - biroz kuting."
        )
    else:
        await message.answer(
            "⚠️ Chekingiz saqlandi, lekin adminga xabar yuborishda muammo bo'ldi. "
            "Iltimos, keyinroq qayta urinib ko'ring."
        )


@router.message(PaymentFlow.waiting_receipt)
async def receipt_wrong_type(message: Message):
    await message.answer("📷 Iltimos, to'lov chekini RASM (skrinshot) ko'rinishida yuboring.")


@router.callback_query(F.data.startswith("pay_approve:"))
async def approve_payment_cb(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return

    payment_id = int(callback.data.split(":", 1)[1])
    result = await db.approve_payment(payment_id, decided_by=callback.from_user.id)
    if not result:
        await callback.answer("Bu to'lov allaqachon hal qilingan.", show_alert=True)
        return

    await callback.answer("✅ Tasdiqlandi")
    if callback.message.caption:
        try:
            await callback.message.edit_caption(
                caption=callback.message.caption + "\n\n✅ TASDIQLANDI",
                reply_markup=None,
            )
        except Exception:
            pass

    plan = config.SUBSCRIPTION_PLANS.get(result.get("plan"), {})
    plan_label = plan.get("label", result.get("plan") or "")
    try:
        await callback.message.bot.send_message(
            result["owner_id"],
            f"✅ To'lovingiz tasdiqlandi! Tarif: {plan_label}.\n"
            f"📅 Obunangiz {result['new_subscription_until']} sanagacha uzaytirildi. Rahmat!",
        )
    except Exception as e:
        logging.warning(f"Egaga ({result['owner_id']}) tasdiq xabarini yuborib bo'lmadi: {e}")


@router.callback_query(F.data.startswith("pay_reject:"))
async def reject_payment_cb(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return

    payment_id = int(callback.data.split(":", 1)[1])
    result = await db.reject_payment(payment_id, decided_by=callback.from_user.id)
    if not result:
        await callback.answer("Bu to'lov allaqachon hal qilingan.", show_alert=True)
        return

    await callback.answer("❌ Rad etildi")
    if callback.message.caption:
        try:
            await callback.message.edit_caption(
                caption=callback.message.caption + "\n\n❌ RAD ETILDI",
                reply_markup=None,
            )
        except Exception:
            pass

    try:
        await callback.message.bot.send_message(
            result["owner_id"],
            "❌ Yuborgan chekingiz rad etildi (noto'g'ri yoki noaniq bo'lishi mumkin). "
            "Iltimos, to'lovni tekshirib, chekni qaytadan yuboring: \"💳 Obuna\" bo'limidan.",
        )
    except Exception as e:
        logging.warning(f"Egaga ({result['owner_id']}) rad etish xabarini yuborib bo'lmadi: {e}")


# ---------- O'ZI RO'YXATDAN O'TGANLAR UCHUN: SINOV MUDDATINI TASDIQLASH ----------

@router.callback_query(F.data.startswith("approve_trial:"))
async def approve_trial_start(callback: CallbackQuery, state: FSMContext):
    """"✅ Tasdiqlash" bosildi - endi admindan necha kunlik sinov muddati
    berishini so'raymiz (erkin son, masalan 14)."""
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return

    target_id = int(callback.data.split(":", 1)[1])
    await callback.answer()

    owner = await db.get_owner(target_id)
    if not owner or owner.get("subscription_status") != "pending_trial":
        await callback.message.answer("Bu so'rov endi topilmadi yoki allaqachon hal qilingan.")
        return

    await state.set_state(ApproveTrial.waiting_days)
    await state.update_data(target_owner_id=target_id)
    await callback.message.answer(
        f"✏️ ID {target_id} uchun necha kunlik bepul sinov muddati berasiz? "
        f"Faqat son yuboring (masalan: {db.SUBSCRIPTION_TRIAL_DAYS})."
    )


@router.message(ApproveTrial.waiting_days)
async def approve_trial_finish(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()
    target_id = data.get("target_owner_id")
    text = (message.text or "").strip()

    if not text.isdigit() or int(text) <= 0:
        await message.answer("Iltimos, musbat butun son yuboring (masalan: 14).")
        return

    days = int(text)
    await state.clear()

    result = await db.approve_trial(target_id, days, decided_by=message.from_user.id)
    if not result:
        await message.answer("Bu so'rov endi topilmadi yoki allaqachon hal qilingan.")
        return

    await message.answer(
        f"✅ ID {target_id} uchun {days} kunlik sinov muddati tasdiqlandi. "
        f"Endi {result['subscription_until']} sanagacha amal qiladi."
    )

    try:
        await message.bot.send_message(
            target_id,
            f"🎉 Tabriklaymiz! Bosh admin sizga {days} kunlik bepul sinov muddatini tasdiqladi.\n"
            f"📅 {result['subscription_until']} sanagacha amal qiladi.\n\n"
            "Davom etish uchun /start buyrug'ini bosing.",
        )
    except Exception as e:
        logging.warning(f"Egaga ({target_id}) sinov muddati tasdiqlangani haqida xabar yuborib bo'lmadi: {e}")


@router.callback_query(F.data.startswith("reject_trial:"))
async def reject_trial_cb(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return

    target_id = int(callback.data.split(":", 1)[1])
    ok = await db.reject_trial(target_id, decided_by=callback.from_user.id)
    if not ok:
        await callback.answer("Bu so'rov allaqachon hal qilingan.", show_alert=True)
        return

    await callback.answer("❌ Rad etildi")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    try:
        await callback.message.bot.send_message(
            target_id,
            "❌ Ro'yxatdan o'tish so'rovingiz bosh admin tomonidan rad etildi. "
            "Savolingiz bo'lsa, bosh admin bilan bog'laning.",
        )
    except Exception as e:
        logging.warning(f"Egaga ({target_id}) rad etish xabarini yuborib bo'lmadi: {e}")
