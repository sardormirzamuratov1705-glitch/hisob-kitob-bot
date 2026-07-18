"""WEB APP (SAVDO) - 1-BOSQICH: INFRATUZILMA.

Bu modul "🛒 Savdo" tugmasini Telegram WebApp (Mini App) sifatida ishga
tushirish uchun kerakli hamma narsani o'z ichiga oladi:

1) Statik fayllarni (index.html/app.js/style.css, webapp_static/ papkasidan)
   HTTP orqali uzatish - Telegram WebApp buni brauzer/ichki-view orqali ochadi.
2) Telegram yuborgan "initData"ni tekshirish (HMAC imzo) - shu orqali
   so'rov chindan ham Telegramning o'zidan, va aynan shu foydalanuvchidan
   kelayotganini ISBOTLAYMIZ (soxta so'rovlarning oldi olinadi).
3) Veb-ilova uchun REST API: mahsulotlar ro'yxati va savdoni yakunlash.
   Ikkinchisi handlers/sales.py'dagi perform_sale_transaction() funksiyasini
   chaqiradi - ya'ni ESKI (matn asosidagi) savdo oqimi bilan AYNAN BIR XIL
   biznes qoidalaridan (sklad, kirim yozuvi, shubhali tekshiruv) foydalanadi.

MUHIM: bu - ko'p bosqichli rejaning FAQAT 1-bosqichi. Hozircha faqat asosiy
"bitta mahsulot / oddiy to'lov" ssenariysi qamrab olingan; qolgan
qismlar (chegirma, aralash to'lov, cross-sell taklifi va h.k. veb-app
tarafida) keyingi bosqichlarda qo'shiladi - pastdagi 10-bosqichli rejaga
qarang (shu commitning javobida yuborilgan xabarda).
"""

import hashlib
import hmac
import json
import logging
import time
from urllib.parse import parse_qsl

from aiohttp import web

import config
import database as db
import access_control
from handlers.sales import _sellable_products, perform_sale_transaction

logger = logging.getLogger(__name__)

INIT_DATA_MAX_AGE_SECONDS = 24 * 60 * 60  # 24 soat - shundan eski initData rad etiladi


def _verify_init_data(init_data: str, bot_token: str) -> dict | None:
    """Telegram Mini Apps initData imzosini tekshiradi.
    https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app

    To'g'ri bo'lsa - ichidagi maydonlarni (dict, jumladan "user" json'dan
    ochib olingan) qaytaradi. Noto'g'ri/eski bo'lsa - None."""
    if not init_data:
        return None
    try:
        pairs = dict(parse_qsl(init_data, strict_parsing=True))
    except ValueError:
        return None

    received_hash = pairs.pop("hash", None)
    if not received_hash:
        return None

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        return None

    auth_date = pairs.get("auth_date")
    if auth_date:
        try:
            if time.time() - int(auth_date) > INIT_DATA_MAX_AGE_SECONDS:
                return None
        except ValueError:
            pass

    if "user" in pairs:
        try:
            pairs["user"] = json.loads(pairs["user"])
        except ValueError:
            pairs["user"] = None

    return pairs


async def _authenticate(request: web.Request):
    """So'rov headeridagi (X-Telegram-Init-Data) initData'ni tekshirib,
    shu foydalanuvchining shop_id/branch_id/role/telegram_id'sini qaytaradi.
    Muvaffaqiyatsiz bo'lsa - None (chaqiruvchi 401 qaytarishi kerak)."""
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    parsed = _verify_init_data(init_data, config.BOT_TOKEN)
    if not parsed or not parsed.get("user"):
        return None

    telegram_id = parsed["user"].get("id")
    if not telegram_id:
        return None

    shop_id = await access_control.get_shop_id(telegram_id)
    if shop_id is None:
        return None

    # Faqat HAQIQIY do'kon egasi va sotuvchi savdo qila oladi (bosh admin emas) -
    # get_shop_id yuqorida allaqachon buni ta'minlaydi (adminga shop_id yo'q).
    role = await access_control.get_role(telegram_id)
    branch_id = await access_control.get_branch_id(telegram_id)
    access = await access_control.check_subscription_access(telegram_id)
    if not access.get("allowed"):
        return None

    return {
        "telegram_id": telegram_id,
        "shop_id": shop_id,
        "role": role,
        "branch_id": branch_id,
        "name": parsed["user"].get("first_name", ""),
    }


async def api_me(request: web.Request):
    auth = await _authenticate(request)
    if not auth:
        return web.json_response({"error": "unauthorized"}, status=401)
    return web.json_response({
        "name": auth["name"],
        "role": auth["role"],
    })


async def api_products(request: web.Request):
    auth = await _authenticate(request)
    if not auth:
        return web.json_response({"error": "unauthorized"}, status=401)

    query = request.query.get("q", "")
    products = await _sellable_products(auth["shop_id"], query)
    payload = [
        {
            "id": p["id"],
            "name": p["name"],
            "quantity": p["quantity"],
            "price": p["price"],
            "sell_price": p.get("sell_price"),
            "min_price": p.get("min_price"),
            "discount_price": (db.product_discount_info(p) or {}).get("price"),
        }
        for p in products
    ]
    return web.json_response({"products": payload})


async def api_sale_submit(request: web.Request):
    """Body (JSON): {"items": [{"product_id":.., "qty":.., "price":..}, ...],
    "payment_method": "naqd"|"plastik"|"aralash", "mixed_cash": son (ixtiyoriy)}."""
    auth = await _authenticate(request)
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

        has_discount = bool(db.product_discount_info(product))
        if product.get("min_price") and price < product["min_price"] and not has_discount:
            return web.json_response({
                "error": "price_below_min", "product_id": product_id,
                "min_price": product["min_price"],
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


def create_web_app(bot) -> web.Application:
    """Bitta aiohttp Application yaratadi - unga main.py kerak bo'lsa
    (WEBHOOK_HOST sozlangan bo'lsa) Telegram webhook route'ini ham
    qo'shib qo'yadi. Bu ilova PORT'da doim (polling bo'lsa ham) ishga
    tushiriladi - aks holda WebApp'ning HTTPS manzili ishlamay qoladi."""
    app = web.Application()
    app["bot"] = bot

    app.router.add_get("/api/webapp/me", api_me)
    app.router.add_get("/api/webapp/products", api_products)
    app.router.add_post("/api/webapp/sale", api_sale_submit)

    app.router.add_static("/webapp/", path=config.WEBAPP_STATIC_DIR, show_index=False, name="webapp_static")

    async def health(request):
        return web.json_response({"status": "ok"})

    app.router.add_get("/health", health)

    return app
