"""SAVDO YAKUNI - MINI APP (20-BOSQICH: REFAKTORING).

Bu modul ilgari webapp.py ichida to'g'ridan-to'g'ri yozilgan edi
(1/3/16-bosqichlarda qo'shilgan: asosiy savdo, cross-sell taklifi,
chegirma tekshiruvi tuzatilishi). 20-bosqichda webapp.py'ni "barcha
routerlarni yig'uvchi asosiy fayl"ga aylantirish maqsadida BU YERGA
ko'chirildi - XATTI-HARAKAT BUTUNLAY O'ZGARMADI, faqat joyi o'zgardi.

MUHIM - BIR XILLIK: handlers/sales.py'dagi perform_sale_transaction()
funksiyasini chaqiradi - ya'ni ESKI (matn asosidagi) savdo oqimi bilan
AYNAN BIR XIL biznes qoidalaridan (sklad, kirim yozuvi, shubhali
tekshiruv) foydalanadi.
"""

import json
import logging

from aiohttp import web

import database as db
from handlers.sales import perform_sale_transaction
from webapp_handlers.sklad_core import _product_payload

logger = logging.getLogger(__name__)


async def _require_auth(request: web.Request):
    """webapp._authenticate orqali autentifikatsiya qiladi. Aylanma import
    (webapp.py <-> webapp_handlers/sale.py)dan qochish uchun import shu
    yerda (funksiya ichida) - xavfsiz, chunki bu funksiya faqat so'rov
    kelganda (ya'ni webapp.py TO'LIQ yuklangandan keyin) chaqiriladi."""
    from webapp import _authenticate
    return await _authenticate(request)


async def api_cross_sell(request: web.Request):
    """3-BOSQICH: matnli oqimdagi "💡 Odatda bu tovar(lar) bilan birga
    quyidagilar ham sotib olinadi" taklifi bilan AYNAN BIR XIL
    db.get_cross_sell_suggestions() funksiyasidan foydalanadi - shu orqali
    veb-ilova va matnli oqim bir xil taklif mantig'iga ega bo'ladi.

    Query param: ids=1,2,3 - hozir savatdagi mahsulot id'lari (vergul bilan)."""
    auth = await _require_auth(request)
    if not auth:
        return web.json_response({"error": "unauthorized"}, status=401)

    ids_param = request.query.get("ids", "")
    try:
        product_ids = [int(x) for x in ids_param.split(",") if x.strip()]
    except ValueError:
        return web.json_response({"error": "invalid_ids"}, status=400)

    if not product_ids:
        return web.json_response({"suggestions": []})

    suggestions = await db.get_cross_sell_suggestions(auth["shop_id"], product_ids)
    payload = [_product_payload(s["product"]) for s in suggestions]
    return web.json_response({"suggestions": payload})


async def api_sale_submit(request: web.Request):
    """Body (JSON): {"items": [{"product_id":.., "qty":.., "price":..}, ...],
    "payment_method": "naqd"|"plastik"|"aralash", "mixed_cash": son (ixtiyoriy)}."""
    auth = await _require_auth(request)
    if not auth:
        return web.json_response({"error": "unauthorized"}, status=401)

    try:
        body = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "invalid_json"}, status=400)

    items = body.get("items") or []
    payment_method = body.get("payment_method")
    if not items:
        return web.json_response({"error": "empty_cart"}, status=400)
    if payment_method not in ("naqd", "plastik", "aralash"):
        return web.json_response({"error": "invalid_payment_method"}, status=400)

    shop_id = auth["shop_id"]
    results = []
    for item in items:
        try:
            product_id = int(item["product_id"])
            qty = float(item["qty"])
            price = float(item["price"])
        except (KeyError, TypeError, ValueError):
            return web.json_response({"error": "invalid_item"}, status=400)

        product = await db.get_product(shop_id, product_id)
        if not product:
            return web.json_response({"error": "product_not_found", "product_id": product_id}, status=400)
        if qty <= 0:
            return web.json_response({"error": "invalid_quantity", "product_id": product_id}, status=400)
        if qty > product["quantity"]:
            return web.json_response({
                "error": "not_enough_stock", "product_id": product_id,
                "available": product["quantity"],
            }, status=400)

        # 16-BOSQICH: CHEGIRMA TEKSHIRUVI TO'G'IRLANDI. Avval bu yerda
        # "has_discount" FAQAT bool sifatida tekshirilar edi - ya'ni
        # mahsulotda QANDAYDIR faol chegirma bo'lsa, narx tekshiruvi
        # BUTUNLAY o'chib qolar edi (hatto chegirma narxidan ham PASTGA
        # sotish mumkin bo'lib qolardi). Endi chegirma bo'lsa, "eng past
        # narx" sifatida ANIQ chegirma narxining O'ZI ishlatiladi -
        # sotuvchi chegirma narxidan pastga tusha olmaydi, faqat
        # o'sha (yoki undan yuqori) narxda sota oladi.
        discount = db.product_discount_info(product)
        effective_min_price = discount["price"] if discount else product.get("min_price")
        if effective_min_price and price < effective_min_price:
            return web.json_response({
                "error": "price_below_min", "product_id": product_id,
                "min_price": effective_min_price,
            }, status=400)
        if price < product["price"]:
            return web.json_response({
                "error": "price_below_cost", "product_id": product_id,
                "cost_price": product["price"],
            }, status=400)

        results.append({"id": product_id, "name": product["name"], "qty": qty, "price": price})

    mixed_cash = None
    mixed_card = None
    if payment_method == "aralash":
        total = sum(r["qty"] * r["price"] for r in results)
        try:
            mixed_cash = float(body.get("mixed_cash", 0))
        except (TypeError, ValueError):
            return web.json_response({"error": "invalid_mixed_cash"}, status=400)
        if mixed_cash < 0 or mixed_cash > total:
            return web.json_response({"error": "invalid_mixed_cash", "total": total}, status=400)
        mixed_card = total - mixed_cash

    bot = request.app["bot"]
    try:
        outcome = await perform_sale_transaction(
            bot, shop_id, auth["telegram_id"], results, payment_method,
            mixed_cash=mixed_cash, mixed_card=mixed_card, notify_chat_id=auth["telegram_id"],
        )
    except Exception as e:
        logger.exception("WebApp orqali savdoni yakunlashda xato")
        return web.json_response({"error": "internal_error"}, status=500)

    if payment_method == "aralash":
        method_line = f"\nTo'lov turi: 🔀 Aralash (💵 {mixed_cash:.0f} so'm + 💳 {mixed_card:.0f} so'm)"
    else:
        method_label = {"naqd": "💵 Naqd", "plastik": "💳 Plastik"}.get(payment_method, "")
        method_line = f"\nTo'lov turi: {method_label}" if method_label else ""

    try:
        await bot.send_message(
            auth["telegram_id"],
            "✅ Savdo yakunlandi! (Veb-ilova orqali)\n\n" + "\n".join(outcome["lines"]) +
            f"\n\n<b>Jami: {outcome['total']:.0f} so'm</b>{method_line}",
        )
    except Exception as e:
        logger.warning(f"WebApp savdo tasdiqini yuborib bo'lmadi: {e}")

    return web.json_response({"ok": True, "sale_id": outcome["sale_id"], "total": outcome["total"]})


def register_routes(app: web.Application) -> None:
    """webapp.py'ning create_web_app() ichidan chaqiriladi."""
    app.router.add_get("/api/webapp/cross_sell", api_cross_sell)
    app.router.add_post("/api/webapp/sale", api_sale_submit)
