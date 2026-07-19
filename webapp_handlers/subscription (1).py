"""OBUNA / TO'LOV - MINI APP (7-BLOK, 13-BOSQICH: BACKEND).

Bu modul do'kon egasi Mini App'dagi "Obuna" bo'limi orqali:
- joriy obuna holati (qancha kun qolgani) + tariflar ro'yxati va to'lov
  rekvizitlarini ko'rish,
- tarif tanlab, to'lov chekini (rasm) yuborish

qila olishi uchun REST API endpointlarini o'z ichiga oladi.

MUHIM - BIR XILLIK: tariflar/rekvizitlar handlers/subscription.py (bot
tarafi) bilan AYNAN BIR XIL database.py funksiyalaridan (db.get_subscription_plans/
db.get_payment_requisites/db.create_payment/db.get_owner_subscription_access)
foydalanadi. Bosh adminga yuboriladigan xabar ("Yangi to'lov (#...)")
matni va tugmalari (✅ Tasdiqlash / ❌ Rad etish, callback_data
"pay_approve:<id>" / "pay_reject:<id>") ham handlers/subscription.py
dagi bilan AYNAN BIR XIL - shu sababli admin javobini kutish va
approve_payment_cb/reject_payment_cb orqali qayta ishlash TAMOMILA bir
xil ishlaydi, mini app orqali yuborilgan chek ham bot orqali
yuborilgandek qabul qilinadi.

FARQ (screenshot_file_id haqida): bot tarafida chek Telegram chatiga
rasm sifatida yuborilgani uchun file_id TAYYOR holda keladi. Mini
App'dan esa xom rasm baytlari (multipart/form-data) keladi - Telegram
file_id olish uchun avval BIRINCHI adminga shu baytlar bilan rasm
yuborilib, natijada qaytgan file_id barcha keyingi adminlarga (va
db.create_payment'ga) ishlatiladi (bot tarafidagi "bitta file_id -
barcha adminlarga" mantig'i bilan bir xil, faqat manba boshqacha).
Agar birorta ham adminga yuborib bo'lmasa (masalan ADMIN_IDS bo'sh) -
to'lov yozuvi UMUMAN yaratilmaydi va foydalanuvchiga xato qaytariladi
(bot tarafida esa screenshot_file_id qo'lda mavjud bo'lgani uchun
yozuv baribir yaratiladi - bu yerda esa file_id manbai faqat shu
yuborish orqali olingani uchun boshqacha yo'l yo'q).

REJA QOIDASI: hech bir bosqich handlers/*.py yoki database.py ga
tegmaydi - shu sababli kb.payment_decision_kb() import qilinmadi,
o'sha tugmalar shu modul ICHIDA mustaqil nusxa sifatida qayta
yasaldi (webapp_handlers/debts.py dagi _debt_link bilan bir xil
yondashuv).

KIM FOYDALANA OLADI: FAQAT haqiqiy do'kon egasi (bot tarafidagi
is_owner_level() tekshiruvi bilan bir xil - sotuvchi va bosh adminga
bu bo'lim umuman ko'rsatilmaydi).
"""

import logging

from aiohttp import web
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup

import config
import database as db

logger = logging.getLogger(__name__)


async def _require_owner_auth(request: web.Request):
    """webapp._authenticate orqali autentifikatsiya qiladi va FAQAT
    haqiqiy do'kon egasiga ruxsat beradi (sotuvchi va bosh admin RAD
    etiladi) - handlers/subscription.py dagi is_owner_level() tekshiruvi
    bilan bir xil ruxsat qoidasi."""
    from webapp import _authenticate

    auth = await _authenticate(request)
    if not auth:
        return None, web.json_response({"error": "unauthorized"}, status=401)
    if auth["role"] != "owner":
        return None, web.json_response({"error": "owner_only"}, status=403)
    return auth, None


def _payment_decision_kb(payment_id: int) -> InlineKeyboardMarkup:
    """keyboards.payment_decision_kb() bilan AYNAN BIR XIL (callback_data
    formati handlers/subscription.py dagi pay_approve:/pay_reject: bilan
    mos kelishi SHART, aks holda admin tugmani bossa hech narsa
    bo'lmaydi)."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"pay_approve:{payment_id}"),
        InlineKeyboardButton(text="❌ Rad etish", callback_data=f"pay_reject:{payment_id}"),
    ]])


async def api_subscription_get(request: web.Request):
    """GET /api/webapp/subscription - joriy obuna holati + tariflar
    ro'yxati + to'lov rekvizitlari (bot tarafidagi "💳 Obuna" ekrani
    bilan bir xil ma'lumot, bitta so'rovda)."""
    auth, err = await _require_owner_auth(request)
    if err:
        return err
    shop_id = auth["shop_id"]

    owner = await db.get_owner(shop_id)
    access = await db.get_owner_subscription_access(shop_id) or {}
    plans = await db.get_subscription_plans()
    requisites = await db.get_payment_requisites()

    return web.json_response({
        "status": access.get("status"),
        "days_left": access.get("days_left"),
        "subscription_until": (owner or {}).get("subscription_until"),
        "plans": plans,
        "requisites": requisites,
    })


async def api_subscription_pay(request: web.Request):
    """POST /api/webapp/subscription/pay - multipart/form-data:
    {"plan": "1m"|"3m"|"12m", "photo": <rasm fayli>}. Muvaffaqiyatli
    bo'lsa "kutilayotgan" to'lov yaratiladi va bosh adminlarga
    tasdiqlash/rad etish tugmalari bilan yuboriladi (handlers/subscription.py
    dagi receipt_received() bilan bir xil natija)."""
    auth, err = await _require_owner_auth(request)
    if err:
        return err

    try:
        post = await request.post()
    except Exception:
        return web.json_response({"error": "invalid_form"}, status=400)

    plan_key = post.get("plan")
    plans = await db.get_subscription_plans()
    plan = plans.get(plan_key)
    if not plan:
        return web.json_response({"error": "invalid_plan"}, status=400)

    photo_field = post.get("photo")
    if photo_field is None or not hasattr(photo_field, "file"):
        return web.json_response({"error": "missing_photo"}, status=400)

    photo_bytes = photo_field.file.read()
    if not photo_bytes:
        return web.json_response({"error": "empty_photo"}, status=400)

    owner = await db.get_owner(auth["telegram_id"])
    owner_label = (owner or {}).get("shop_name") or (owner or {}).get("owner_name") \
        or auth.get("name") or str(auth["telegram_id"])
    price_text = f"{plan['price']:,}".replace(",", " ")

    bot = request.app["bot"]
    file_id = None
    sent_to_any_admin = False
    payment_id = None
    admin_caption_template = (
        "💳 <b>Yangi to'lov (#{payment_id})</b>\n\n"
        f"🏪 {owner_label} (ID: {auth['telegram_id']})\n"
        f"📦 Tarif: {plan['label']} — {price_text} so'm ({plan['days']} kun)\n\n"
        "Chekni tekshirib, tasdiqlang yoki rad eting:"
    )

    for admin_id in config.ADMIN_IDS:
        try:
            if file_id is None:
                # Birinchi adminga xom baytlar bilan yuboriladi - shu
                # javobdan file_id olinadi (payment_id hali yo'q, shuning
                # uchun caption/tugmalarsiz - pastda payment yaratilgach
                # shu XABARNI tahrirlab caption/tugma qo'shiladi).
                sent = await bot.send_photo(admin_id, photo=BufferedInputFile(photo_bytes, filename="chek.jpg"))
                file_id = sent.photo[-1].file_id

                payment_id = await db.create_payment(
                    owner_id=auth["telegram_id"], amount=plan["price"], plan=plan_key,
                    days=plan["days"], screenshot_file_id=file_id,
                )
                try:
                    await bot.edit_message_caption(
                        chat_id=admin_id, message_id=sent.message_id,
                        caption=admin_caption_template.format(payment_id=payment_id),
                        parse_mode="HTML", reply_markup=_payment_decision_kb(payment_id),
                    )
                except Exception as e:
                    logger.warning(f"Birinchi admin ({admin_id}) xabarini tahrirlab bo'lmadi: {e}")
            else:
                await bot.send_photo(
                    admin_id, photo=file_id,
                    caption=admin_caption_template.format(payment_id=payment_id),
                    parse_mode="HTML", reply_markup=_payment_decision_kb(payment_id),
                )
            sent_to_any_admin = True
        except Exception as e:
            logger.warning(f"Adminga ({admin_id}) chek yuborib bo'lmadi: {e}")

    if not sent_to_any_admin or not payment_id:
        return web.json_response({"error": "admin_unreachable"}, status=502)

    return web.json_response({"payment_id": payment_id})


def register_routes(app: web.Application) -> None:
    """webapp.py'ning create_web_app() ichidan chaqiriladi - shu
    modulning barcha route'larini bitta joyda ro'yxatdan o'tkazadi."""
    app.router.add_get("/api/webapp/subscription", api_subscription_get)
    app.router.add_post("/api/webapp/subscription/pay", api_subscription_pay)
