"""SOZLAMALAR - MINI APP (6-BLOK, 11-BOSQICH: BACKEND).

Bu modul do'kon egasi/sotuvchi Mini App'dagi "Sozlamalar" bo'limi orqali
o'zi haqidagi profil ma'lumotlarini (bot tarafida /start onboarding
paytida bir marta so'raladigan, keyin qayta tahrirlash imkoni bo'lmagan
maydonlarni) ko'rish va tahrirlash qila olishi uchun REST API
endpointlarini o'z ichiga oladi:

- do'kon egasi: ismi, do'kon nomi, telefon raqami
  (db.get_owner / db.set_owner_profile - handlers/start.py dagi
  OwnerOnboarding bilan AYNAN BIR XIL funksiyalar).
- sotuvchi: ismi, telefon raqami
  (db.get_seller / db.set_seller_profile - handlers/start.py dagi
  SellerOnboarding bilan AYNAN BIR XIL funksiyalar).

MUHIM - BIR XILLIK: validatsiya ham handlers/start.py dagi onboarding
bilan bir xil - faqat bo'sh bo'lmagan matn talab qilinadi (.strip()),
qo'shimcha format tekshiruvi yo'q (bot tarafida ham yo'q).

REJA QOIDASI: hech bir bosqich handlers/*.py yoki database.py ga tegmaydi -
shu sababli bu yerda ham FAQAT allaqachon mavjud bo'lgan db.get_owner /
db.set_owner_profile / db.get_seller / db.set_seller_profile
funksiyalaridan foydalaniladi, hech qanday yangi ustun/jadval kerak emas.

KIM FOYDALANA OLADI: do'kon egasi HAM, sotuvchi HAM (bosh admin EMAS -
uning bunday profili yo'q) - webapp_handlers/debts.py va
webapp_handlers/transactions.py dagi _require_shop_auth bilan bir xil
mantiq (rol asosida turli maydonlar qaytariladi/yangilanadi).
"""

import logging

from aiohttp import web

import database as db

logger = logging.getLogger(__name__)


async def _require_shop_auth(request: web.Request):
    """webapp._authenticate orqali autentifikatsiya qiladi va do'kon
    egasi YOKI sotuvchiga (lekin bosh adminga EMAS) ruxsat beradi - xuddi
    webapp_handlers/debts.py va webapp_handlers/transactions.py dagi bir
    xil nomli funksiya kabi (aylanma import haqidagi izoh ham o'sha
    yerdagi bilan bir xil sabab)."""
    from webapp import _authenticate

    auth = await _authenticate(request)
    if not auth:
        return None, web.json_response({"error": "unauthorized"}, status=401)
    if auth["role"] not in ("owner", "seller"):
        return None, web.json_response({"error": "not_applicable"}, status=404)
    return auth, None


async def api_settings_get(request: web.Request):
    """GET /api/webapp/settings - joriy foydalanuvchining o'z profili
    (rolga qarab do'kon egasi yoki sotuvchi jadvalidan)."""
    auth, err = await _require_shop_auth(request)
    if err:
        return err

    if auth["role"] == "owner":
        owner = await db.get_owner(auth["telegram_id"])
        if not owner:
            return web.json_response({"error": "not_found"}, status=404)
        return web.json_response({
            "role": "owner",
            "owner_name": owner.get("owner_name") or "",
            "shop_name": owner.get("shop_name") or "",
            "phone_number": owner.get("phone_number") or "",
        })

    seller = await db.get_seller(auth["telegram_id"])
    if not seller:
        return web.json_response({"error": "not_found"}, status=404)
    return web.json_response({
        "role": "seller",
        "seller_name": seller.get("seller_name") or "",
        "phone_number": seller.get("phone_number") or "",
    })


async def api_settings_update(request: web.Request):
    """POST /api/webapp/settings - body rolga qarab farq qiladi:
    - owner: {"owner_name", "shop_name", "phone_number"} - uchalasi ham
      bo'sh bo'lmagan matn bo'lishi kerak (onboarding bilan bir xil).
    - seller: {"seller_name", "phone_number"} - ikkalasi ham bo'sh
      bo'lmagan matn bo'lishi kerak."""
    auth, err = await _require_shop_auth(request)
    if err:
        return err

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid_json"}, status=400)

    if auth["role"] == "owner":
        owner_name = (body.get("owner_name") or "").strip()
        shop_name = (body.get("shop_name") or "").strip()
        phone_number = (body.get("phone_number") or "").strip()
        if not owner_name or not shop_name or not phone_number:
            return web.json_response({"error": "empty_field"}, status=400)

        await db.set_owner_profile(auth["telegram_id"], owner_name, shop_name, phone_number)
        return web.json_response({
            "role": "owner",
            "owner_name": owner_name,
            "shop_name": shop_name,
            "phone_number": phone_number,
        })

    seller_name = (body.get("seller_name") or "").strip()
    phone_number = (body.get("phone_number") or "").strip()
    if not seller_name or not phone_number:
        return web.json_response({"error": "empty_field"}, status=400)

    await db.set_seller_profile(auth["telegram_id"], seller_name, phone_number)
    return web.json_response({
        "role": "seller",
        "seller_name": seller_name,
        "phone_number": phone_number,
    })


def register_routes(app: web.Application) -> None:
    """webapp.py'ning create_web_app() ichidan chaqiriladi - shu
    modulning barcha route'larini bitta joyda ro'yxatdan o'tkazadi."""
    app.router.add_get("/api/webapp/settings", api_settings_get)
    app.router.add_post("/api/webapp/settings", api_settings_update)
