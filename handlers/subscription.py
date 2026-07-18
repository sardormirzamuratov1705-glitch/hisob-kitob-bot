from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

import config
import keyboards as kb
from access_control import is_admin, is_owner_level

router = Router()


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
    await message.answer(TARIFFS_TEXT, reply_markup=kb.subscription_plans_menu())


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
    plan = config.SUBSCRIPTION_PLANS.get(plan_key)
    if not plan:
        await callback.message.answer("❌ Bu tarif topilmadi. Qaytadan urinib ko'ring: /start")
        return

    # 7-bosqichda chek skrinshotini qabul qiladigan handler shu yerdan
    # tanlangan tarifni state orqali oladi (state.get_data()["subscription_plan"]).
    await state.update_data(subscription_plan=plan_key)

    price_text = f"{plan['price']:,}".replace(",", " ")
    text = (
        f"✅ Siz <b>{plan['label']}</b> tarifini tanladingiz — {price_text} so'm.\n\n"
        "💳 To'lov rekvizitlari:\n"
        f"• Karta: <code>{config.PAYMENT_CARD_NUMBER}</code> ({config.PAYMENT_CARD_HOLDER})\n"
        f"• Click: {config.PAYMENT_CLICK_NUMBER}\n"
        f"• Payme: {config.PAYMENT_PAYME_NUMBER}\n\n"
        "To'lovni amalga oshirgach, chek/skrinshotni shu yerga rasm qilib yuboring - "
        "u bosh adminga tekshirish uchun boradi va tasdiqlangach obunangiz "
        "avtomatik uzaytiriladi."
    )
    await callback.message.answer(text)
