"""YANGI: "🏠 Bosh sahifa" - MINI APP DASHBOARD (BACKEND).

Foydalanuvchi taqdim etgan 5 ta dizayn namunasidagi "Bosh sahifa"
ekranining backend qismi: bitta so'rovda ekranga kerakli barcha qisqa
statistikani (bugungi savdo, o'sish foizi, bugun sotilgan mahsulot,
sklad qoldig'i, qarzdorlar summasi, kam qolgan mahsulotlar soni)
qaytaradi.

Frontend: webapp_static/index.html #screen-home,
webapp_static/app.js loadDashboard()/renderDashboard().

MUHIM - BIR XILLIK: boshqa modullar bilan bir xil qoida - do'kon egasi
HAM, sotuvchi HAM ko'radi (bosh admin ko'rmaydi - uning shop_id'si yo'q,
qarang: webapp.py._authenticate)."""

import logging

from aiohttp import web

import database as db

logger = logging.getLogger(__name__)

# YANGI: Bosh sahifa menyusidagi 8 ta tugmadan qaysilarini do'kon egasi
# sotuvchidan yashirishi MUMKIN (Kassa/Qarzdorlar har doim ochiq -
# kundalik savdo uchun shart, ro'yxatdan chiqarilmaydi; Filiallar esa
# Profil ekranining o'zida allaqachon strukturaviy ravishda faqat
# do'kon egasiga ko'rinadi, shuning uchun bu yerda alohida tanlanmaydi).
TOGGLEABLE_HOME_ACTIONS = ("sklad", "reports", "ai", "restock", "settings")


async def _require_shop_auth(request: web.Request):
    """webapp._authenticate orqali autentifikatsiya qiladi va do'kon
    egasi YOKI sotuvchiga (lekin bosh adminga EMAS) ruxsat beradi - xuddi
    webapp_handlers/reports.py dagi bir xil nomli funksiya kabi (aylanma
    import haqidagi izoh ham o'sha yerdagi bilan bir xil sabab)."""
    from webapp import _authenticate

    auth = await _authenticate(request)
    if not auth:
        return None, web.json_response({"error": "unauthorized"}, status=401)
    if auth["role"] not in ("owner", "seller"):
        return None, web.json_response({"error": "not_applicable"}, status=404)
    return auth, None


async def _require_owner_auth(request: web.Request):
    """Yuqoridagi bilan bir xil, lekin FAQAT haqiqiy do'kon egasiga
    ruxsat beradi (sotuvchi o'ziga qaysi tugmalar ko'rinishini o'zi
    belgilay olmasligi kerak)."""
    auth, err = await _require_shop_auth(request)
    if err:
        return None, err
    if auth["role"] != "owner":
        return None, web.json_response({"error": "not_applicable"}, status=404)
    return auth, None


async def api_dashboard(request: web.Request):
    """GET /api/webapp/dashboard - qarang: database.get_dashboard_stats()."""
    auth, err = await _require_shop_auth(request)
    if err:
        return err

    stats = await db.get_dashboard_stats(auth["shop_id"])
    stats["name"] = auth["name"]
    # Sotuvchi uchun - do'kon egasi Sozlamalardan yashirgan tugmalar
    # ro'yxati (do'kon egasining o'ziga hech narsa yashirilmaydi).
    stats["hidden_home_actions"] = (
        [] if auth["role"] == "owner" else await db.get_seller_home_menu_hidden(auth["shop_id"])
    )
    return web.json_response(stats)


async def api_seller_menu_get(request: web.Request):
    """GET /api/webapp/dashboard/seller-menu - FAQAT do'kon egasi uchun:
    hozirgi yashirilgan tugmalar + tanlash mumkin bo'lgan barcha
    tugmalar ro'yxati (Profil ekranidagi sozlamalar oynasi shu ikkalasini
    checkbox ro'yxati sifatida chizadi)."""
    auth, err = await _require_owner_auth(request)
    if err:
        return err

    hidden = await db.get_seller_home_menu_hidden(auth["shop_id"])
    return web.json_response({"hidden": hidden, "options": list(TOGGLEABLE_HOME_ACTIONS)})


async def api_seller_menu_update(request: web.Request):
    """POST /api/webapp/dashboard/seller-menu - body: {"hidden": [...]}.
    Faqat TOGGLEABLE_HOME_ACTIONS ichidagi kalitlarni qabul qiladi -
    boshqa har qanday qiymat (masalan "sale"/"debts") jim o'tkazib
    yuboriladi, shuning uchun kimdir noto'g'ri so'rov yuborsa ham
    kundalik savdo uchun shart bo'lgan tugmalar yashirilib qolmaydi."""
    auth, err = await _require_owner_auth(request)
    if err:
        return err

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid_json"}, status=400)

    raw_hidden = body.get("hidden")
    if not isinstance(raw_hidden, list):
        return web.json_response({"error": "invalid_body"}, status=400)

    hidden = [x for x in raw_hidden if x in TOGGLEABLE_HOME_ACTIONS]
    await db.set_seller_home_menu_hidden(auth["shop_id"], hidden)
    return web.json_response({"hidden": hidden, "options": list(TOGGLEABLE_HOME_ACTIONS)})


def register_routes(app: web.Application) -> None:
    """webapp.py'ning create_web_app() ichidan chaqiriladi."""
    app.router.add_get("/api/webapp/dashboard", api_dashboard)
    app.router.add_get("/api/webapp/dashboard/seller-menu", api_seller_menu_get)
    app.router.add_post("/api/webapp/dashboard/seller-menu", api_seller_menu_update)
