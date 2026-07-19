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


async def api_dashboard(request: web.Request):
    """GET /api/webapp/dashboard - qarang: database.get_dashboard_stats()."""
    auth, err = await _require_shop_auth(request)
    if err:
        return err

    stats = await db.get_dashboard_stats(auth["shop_id"])
    stats["name"] = auth["name"]
    return web.json_response(stats)


def register_routes(app: web.Application) -> None:
    """webapp.py'ning create_web_app() ichidan chaqiriladi."""
    app.router.add_get("/api/webapp/dashboard", api_dashboard)
