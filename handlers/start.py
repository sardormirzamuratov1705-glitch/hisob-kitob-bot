import logging

from aiogram import Router, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

import database as db
import keyboards as kb
from access_control import is_admin, is_authorized, get_role

router = Router()


# ---------- NOTANISH ODAM UCHUN "LANDING" OYNA ----------
# Hali bazada umuman yo'q (na admin, na owner, na seller) har qanday kishi
# /start bossa - shu oyna ko'rsatiladi: bot nima qila olishi haqida qisqa
# tanishtiruv + "Ro'yxatdan o'tish" tugmasi. O'zi tugmani bosishi bilan
# ro'yxatdan o'tish oqimi (ism/do'kon nomi/telefon so'rash va 14 kunlik
# trial boshlash) 3-bosqichda ulanadi - hozircha faqat tugma va uning
# joyini tayyorlaymiz.

LANDING_TEXT = (
    "👋 Assalomu alaykum!\n\n"
    "Bu — do'kon egalari uchun hisob-kitob boti. U yordamida siz:\n\n"
    "📦 <b>Sklad</b> — mahsulotlar va qoldiqlarni yuritasiz\n"
    "💰 <b>Kirim/Chiqim</b> — pul aylanmasini nazorat qilasiz\n"
    "📒 <b>Qarz daftar</b> — mijozlar qarzini yozib, eslatma yuborasiz\n"
    "📊 <b>Hisobot</b> — savdo va foyda bo'yicha hisobotlar olasiz\n"
    "🏢 <b>Filiallar</b> — bir nechta do'kon/filialni bitta joydan boshqarasiz\n\n"
    "Boshlash uchun quyidagi tugmani bosing 👇"
)


async def _send_landing(message: Message):
    await message.answer(LANDING_TEXT, reply_markup=kb.landing_menu())


@router.callback_query(F.data == "self_register")
async def self_register_start(callback: CallbackQuery, state: FSMContext):
    # TODO (3-bosqich): bu yerda haqiqiy o'z-o'zidan ro'yxatdan o'tish
    # so'rovnomasi (ism, do'kon nomi, telefon) boshlanadi va yangi do'kon
    # egasi 14 kunlik trial bilan avtomatik yaratiladi.
    await callback.answer()
    await callback.message.answer(
        "📝 Ro'yxatdan o'tish tez orada shu yerda ochiladi. Iltimos, kuting."
    )


# ---------- DO'KON EGASI UCHUN QISQA SO'ROVNOMA ----------
# Yangi do'kon egasi (link orqali yoki bosh admin tomonidan forward/ID bilan
# qo'shilgan bo'lsin - farqi yo'q) birinchi marta botga /start bosganda,
# ismi va do'koni nomi/turi so'raladi. Bu bosh adminga bir nechta do'kon
# egasini Telegram ID/username emas, balki tanish nom bilan ajratib
# ko'rish imkonini beradi ("📋 Do'kon egalari ro'yxati"da ko'rinadi).

class OwnerOnboarding(StatesGroup):
    waiting_owner_name = State()
    waiting_shop_name = State()
    waiting_phone = State()


async def _start_owner_onboarding(message: Message, state: FSMContext):
    await state.set_state(OwnerOnboarding.waiting_owner_name)
    await message.answer(
        "Yana ikkita qisqa savol qoldi - bu bosh adminga do'konlarni "
        "bir-biridan oson ajratishga yordam beradi.\n\n"
        "👤 Ismingizni (yoki F.I.Sh) kiriting:"
    )


@router.message(OwnerOnboarding.waiting_owner_name)
async def owner_onboarding_name(message: Message, state: FSMContext):
    if not await db.is_owner(message.from_user.id):
        await state.clear()
        return
    if not message.text:
        await message.answer("Iltimos, ismingizni matn ko'rinishida kiriting.")
        return

    await state.update_data(owner_name=message.text.strip())
    await state.set_state(OwnerOnboarding.waiting_shop_name)
    await message.answer(
        "🏪 Endi do'koningiz nomi yoki turini kiriting "
        "(masalan: \"Bahor market\" yoki \"Oziq-ovqat do'koni\"):"
    )


@router.message(OwnerOnboarding.waiting_shop_name)
async def owner_onboarding_shop(message: Message, state: FSMContext):
    if not await db.is_owner(message.from_user.id):
        await state.clear()
        return
    if not message.text:
        await message.answer("Iltimos, do'koningiz nomi yoki turini matn ko'rinishida kiriting.")
        return

    await state.update_data(shop_name=message.text.strip())
    await state.set_state(OwnerOnboarding.waiting_phone)
    await message.answer(
        "📞 Endi telefon raqamingizni kiriting (masalan: +998901234567):"
    )


@router.message(OwnerOnboarding.waiting_phone)
async def owner_onboarding_phone(message: Message, state: FSMContext):
    if not await db.is_owner(message.from_user.id):
        await state.clear()
        return

    phone_number = None
    if message.contact and message.contact.phone_number:
        phone_number = message.contact.phone_number
    elif message.text:
        phone_number = message.text.strip()
    else:
        await message.answer("Iltimos, telefon raqamingizni matn ko'rinishida kiriting.")
        return

    data = await state.get_data()
    owner_name = data.get("owner_name")
    shop_name = data.get("shop_name")
    await db.set_owner_profile(message.from_user.id, owner_name, shop_name, phone_number)
    await state.clear()

    await message.answer(
        f"✅ Rahmat! Ma'lumotlar saqlandi:\n👤 {owner_name}\n🏪 {shop_name}\n📞 {phone_number}\n\n"
        "Quyidagi bo'limlardan birini tanlang:",
        reply_markup=kb.main_menu("owner"),
    )


# ---------- SOTUVCHI UCHUN QISQA SO'ROVNOMA ----------
# Xuddi do'kon egasidagi kabi - yangi sotuvchi (link orqali yoki do'kon
# egasi tomonidan forward/ID bilan qo'shilgan bo'lsin) birinchi marta
# /start bosganda, ismi va telefon raqami so'raladi. Do'kon nomi so'ralmaydi,
# chunki sotuvchi allaqachon ma'lum bir do'konga (shop_id) biriktirilgan.

class SellerOnboarding(StatesGroup):
    waiting_seller_name = State()
    waiting_phone = State()


async def _start_seller_onboarding(message: Message, state: FSMContext):
    await state.set_state(SellerOnboarding.waiting_seller_name)
    await message.answer(
        "Yana ikkita qisqa savol qoldi - bu do'kon egasiga sotuvchilarni "
        "bir-biridan oson ajratishga yordam beradi.\n\n"
        "👤 Ismingizni (yoki F.I.Sh) kiriting:"
    )


@router.message(SellerOnboarding.waiting_seller_name)
async def seller_onboarding_name(message: Message, state: FSMContext):
    if not await db.is_seller(message.from_user.id):
        await state.clear()
        return
    if not message.text:
        await message.answer("Iltimos, ismingizni matn ko'rinishida kiriting.")
        return

    await state.update_data(seller_name=message.text.strip())
    await state.set_state(SellerOnboarding.waiting_phone)
    await message.answer("📞 Endi telefon raqamingizni kiriting (masalan: +998901234567):")


@router.message(SellerOnboarding.waiting_phone)
async def seller_onboarding_phone(message: Message, state: FSMContext):
    if not await db.is_seller(message.from_user.id):
        await state.clear()
        return

    phone_number = None
    if message.contact and message.contact.phone_number:
        phone_number = message.contact.phone_number
    elif message.text:
        phone_number = message.text.strip()
    else:
        await message.answer("Iltimos, telefon raqamingizni matn ko'rinishida kiriting.")
        return

    data = await state.get_data()
    seller_name = data.get("seller_name")
    await db.set_seller_profile(message.from_user.id, seller_name, phone_number)
    await state.clear()

    await message.answer(
        f"✅ Rahmat! Ma'lumotlar saqlandi:\n👤 {seller_name}\n📞 {phone_number}\n\n"
        "Quyidagi bo'limlardan birini tanlang:",
        reply_markup=kb.main_menu("seller"),
    )


@router.message(CommandStart(deep_link=True))
async def cmd_start_deep_link(message: Message, state: FSMContext, command: CommandObject):
    """Mijoz "Qarz qo'shish" bo'limida yaratilgan shaxsiy link orqali
    (t.me/bot?start=debt_<id>) botni ochganda, yoki do'kon egasi/sotuvchi
    bir martalik taklif linki orqali botni ochganda ishga tushadi."""
    await state.clear()
    payload = command.args or ""

    if payload.startswith("owner_"):
        token = payload.split("_", 1)[1]
        invite = await db.get_owner_invite(token)

        if not invite:
            await message.answer("❌ Bu link amal qilmaydi (noto'g'ri yoki eskirgan).")
            return
        if invite.get("used_by"):
            await message.answer(
                "❌ Bu link allaqachon ishlatilgan. Har bir taklif linki faqat "
                "BITTA marta, bitta odam uchun amal qiladi. Yangi link so'rang."
            )
            return

        if is_admin(message.from_user.id):
            await message.answer("Siz allaqachon bosh adminsiz - bu link sizga kerak emas.")
            return
        if await db.is_owner(message.from_user.id):
            await message.answer("Siz allaqachon do'kon egasi sifatida ro'yxatdasiz.")
            return
        if await db.is_seller(message.from_user.id):
            await message.answer("Siz allaqachon bir do'konga sotuvchi sifatida ulangansiz.")
            return

        # Race-safe: agar shu vaqtda boshqa birov ham xuddi shu tokenni
        # ishlatmoqchi bo'lsa, faqat biri muvaffaqiyatli bo'ladi.
        claimed = await db.use_owner_invite(token, message.from_user.id)
        if not claimed:
            await message.answer(
                "❌ Bu link boshqa birov tomonidan sizdan bir zum oldin ishlatib bo'lingan."
            )
            return

        await db.add_owner(
            message.from_user.id,
            message.from_user.full_name,
            message.from_user.username,
            added_by=invite["created_by"],
        )
        await message.answer(
            "✅ Tabriklaymiz! Siz do'kon egasi sifatida ro'yxatdan o'tdingiz."
        )
        try:
            await message.bot.send_message(
                invite["created_by"],
                f"✅ Yangi do'kon egasi taklif linki orqali qo'shildi: "
                f"{message.from_user.full_name} (ID: {message.from_user.id})",
            )
        except Exception as e:
            logging.warning(f"Adminga xabar yuborib bo'lmadi: {e}")
        await _start_owner_onboarding(message, state)
        return

    if payload.startswith("seller_"):
        token = payload.split("_", 1)[1]
        invite = await db.get_seller_invite(token)

        if not invite:
            await message.answer("❌ Bu link amal qilmaydi (noto'g'ri yoki eskirgan).")
            return
        if invite.get("used_by"):
            await message.answer(
                "❌ Bu link allaqachon ishlatilgan. Har bir taklif linki faqat "
                "BITTA marta, bitta odam uchun amal qiladi. Yangi link so'rang."
            )
            return

        if is_admin(message.from_user.id):
            await message.answer("Siz bosh adminsiz - bu link sizga kerak emas.")
            return
        if await db.is_owner(message.from_user.id):
            await message.answer("Siz allaqachon do'kon egasisiz - bu link sizga kerak emas.")
            return
        if await db.is_seller(message.from_user.id):
            await message.answer("Siz allaqachon bir do'konga sotuvchi sifatida ulangansiz.")
            return

        claimed = await db.use_seller_invite(token, message.from_user.id)
        if not claimed:
            await message.answer(
                "❌ Bu link boshqa birov tomonidan sizdan bir zum oldin ishlatib bo'lingan."
            )
            return

        await db.add_seller(
            message.from_user.id,
            invite["shop_id"],
            message.from_user.full_name,
            message.from_user.username,
            added_by=invite["created_by"],
            branch_id=invite.get("branch_id"),
        )
        await message.answer(
            "✅ Tabriklaymiz! Siz sotuvchi sifatida ro'yxatdan o'tdingiz."
        )
        try:
            await message.bot.send_message(
                invite["created_by"],
                f"✅ Yangi sotuvchi taklif linki orqali qo'shildi: "
                f"{message.from_user.full_name} (ID: {message.from_user.id})",
            )
        except Exception as e:
            logging.warning(f"Do'kon egasiga xabar yuborib bo'lmadi: {e}")
        await _start_seller_onboarding(message, state)
        return

    if payload.startswith("debt_"):
        try:
            debt_id = int(payload.split("_", 1)[1])
        except ValueError:
            debt_id = None

        # Diqqat: bu yerda hali shop_id noma'lum (mijoz hech qanday do'konga
        # a'zo emas), shuning uchun shop_id talab qilmaydigan get_debt_by_id
        # ishlatiladi.
        debt = await db.get_debt_by_id(debt_id) if debt_id else None
        if debt:
            await db.link_debt_customer(
                debt_id,
                message.from_user.id,
                message.from_user.username,
            )
            await message.answer(
                "✅ Xush kelibsiz! Endi qarzdorlik va to'lovlar haqida eslatmalarni "
                "shu bot orqali olasiz."
            )

            # MUHIM: faqat shu qarz tegishli bo'lgan DO'KON EGASIGA xabar beramiz,
            # boshqa do'kon egalariga yoki bosh adminga emas - aks holda boshqa
            # do'konlar bu mijoz va uning qarzi haqida bilib qolar edi.
            shop_owner_id = debt.get("shop_id")
            if shop_owner_id:
                try:
                    await message.bot.send_message(
                        shop_owner_id,
                        f"🔗 <b>{debt['customer_name']}</b> shaxsiy link orqali botga ulandi.\n"
                        f"Endi unga to'g'ridan-to'g'ri eslatma yuborish mumkin.",
                        parse_mode="HTML",
                    )
                except Exception as e:
                    logging.warning(f"Do'kon egasiga xabar yuborib bo'lmadi ({shop_owner_id}): {e}")
            return

    # Noto'g'ri yoki eskirgan link bo'lsa, oddiy /start kabi davom etamiz.
    role = await get_role(message.from_user.id)
    if role is None:
        await _send_landing(message)
        return
    if role == "owner":
        owner = await db.get_owner(message.from_user.id)
        if owner and not owner.get("owner_name"):
            await message.answer("Assalomu alaykum! Do'kon boshqaruv botiga xush kelibsiz.")
            await _start_owner_onboarding(message, state)
            return
    if role == "seller":
        seller = await db.get_seller(message.from_user.id)
        if seller and not seller.get("seller_name"):
            await message.answer("Assalomu alaykum! Do'kon boshqaruv botiga xush kelibsiz.")
            await _start_seller_onboarding(message, state)
            return
    await message.answer(
        "Assalomu alaykum! Do'kon boshqaruv botiga xush kelibsiz.\n\n"
        "Quyidagi bo'limlardan birini tanlang:",
        reply_markup=kb.main_menu(role)
    )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    role = await get_role(message.from_user.id)
    if role is None:
        await _send_landing(message)
        return
    if role == "owner":
        # Do'kon egasi hali ismi/do'kon nomini kiritmagan bo'lsa (masalan,
        # bosh admin uni forward/ID orqali qo'shgan va u birinchi marta
        # /start bosyapti) - avval qisqa so'rovnomani to'ldirtiramiz.
        owner = await db.get_owner(message.from_user.id)
        if owner and not owner.get("owner_name"):
            await message.answer("Assalomu alaykum! Do'kon boshqaruv botiga xush kelibsiz.")
            await _start_owner_onboarding(message, state)
            return
    if role == "seller":
        # Xuddi shunday - sotuvchi ham do'kon egasi tomonidan forward/ID orqali
        # qo'shilgan bo'lsa, birinchi /start'da ismi/telefonini kiritadi.
        seller = await db.get_seller(message.from_user.id)
        if seller and not seller.get("seller_name"):
            await message.answer("Assalomu alaykum! Do'kon boshqaruv botiga xush kelibsiz.")
            await _start_seller_onboarding(message, state)
            return
    await message.answer(
        "Assalomu alaykum! Do'kon boshqaruv botiga xush kelibsiz.\n\n"
        "Quyidagi bo'limlardan birini tanlang:",
        reply_markup=kb.main_menu(role)
    )


@router.message(F.text == "⬅️ Orqaga")
async def go_back(message: Message, state: FSMContext):
    await state.clear()
    role = await get_role(message.from_user.id)
    if role is None:
        return
    await message.answer("Asosiy menyu:", reply_markup=kb.main_menu(role))


# Quyidagi bo'limlar (Sklad, Kirim/Chiqim, Hisobot, Sotuvchilar) faqat
# HAQIQIY do'kon egalariga tegishli - na bosh adminda, na sotuvchida bunga
# ruxsat yo'q. kb.main_menu() bu tugmalarni ularga umuman ko'rsatmaydi,
# lekin himoyani ikki marta ta'minlash uchun (masalan eski chatdan matnni
# qayta yuborsa) har bir handlerda ham qayta tekshiramiz.

async def _require_owner_only(message: Message) -> bool:
    if not await db.is_owner(message.from_user.id):
        await message.answer("Bu bo'lim faqat do'kon egasi uchun.")
        return False
    return True


# "📒 Qarz daftar" esa do'kon egasi VA sotuvchi uchun ham ochiq (faqat bosh
# admin kira olmaydi) - qarz qo'shish/to'lov qabul qilish sotuvchining
# kundalik ishi.

async def _require_shop_access(message: Message) -> bool:
    if is_admin(message.from_user.id):
        await message.answer("Bu bo'lim faqat do'kon egalari uchun.")
        return False
    return True


@router.message(F.text == "📦 Sklad")
async def open_sklad(message: Message, state: FSMContext):
    await state.clear()
    if not await _require_owner_only(message):
        return
    await message.answer("Sklad bo'limi:", reply_markup=kb.sklad_menu())


@router.message(F.text == "💰 Kirim/Chiqim")
async def open_kirim_chiqim(message: Message, state: FSMContext):
    await state.clear()
    if not await _require_owner_only(message):
        return
    await message.answer("Kirim/Chiqim bo'limi:", reply_markup=kb.kirim_chiqim_menu())


@router.message(F.text == "📒 Qarz daftar")
async def open_qarz(message: Message, state: FSMContext):
    await state.clear()
    if not await _require_shop_access(message):
        return
    await message.answer("Qarz daftar bo'limi:", reply_markup=kb.qarz_menu())


@router.message(F.text == "📊 Hisobot")
async def open_hisobot(message: Message, state: FSMContext):
    await state.clear()
    if not await _require_owner_only(message):
        return
    await message.answer("Hisobot bo'limi:", reply_markup=kb.hisobot_menu())


# ---------- BOSH ADMIN: ZAXIRA NUSXA ----------
# Butun bazani (BARCHA do'konlar) qamrab oladigan texnik zaxira - shuning
# uchun faqat bosh adminga ochiq (handlers/reports.py'dagi export_db/
# restore_db_start ham o'z ichida is_admin() bilan qayta tekshiradi).

@router.message(F.text == "🗄 Zaxira nusxa")
async def open_backup(message: Message, state: FSMContext):
    await state.clear()
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        "🗄 Zaxira nusxa bo'limi (barcha do'konlar):",
        reply_markup=kb.admin_backup_menu(),
    )
