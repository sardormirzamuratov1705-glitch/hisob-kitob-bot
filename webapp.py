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
from pathlib import Path
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
    Muvaffaqiyatsiz bo'lsa - None (chaqiruvchi 401 qaytarishi kerak).

    DIQQAT: har bir rad etish sababi logga yoziladi (faqat telegram_id/status,
    initData'ning o'zi emas) - aks holda "401" xabarining nima uchun
    chiqayotganini production'da aniqlash imkonsiz bo'lib qolardi."""
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    if not init_data:
        logger.warning("WebApp 401: X-Telegram-Init-Data header bo'sh yoki umuman yo'q "
                        "(WebApp Telegram ICHIDA emas, oddiy brauzerda ochilgan bo'lishi mumkin).")
        return None

    parsed = _verify_init_data(init_data, config.BOT_TOKEN)
    if not parsed or not parsed.get("user"):
        logger.warning("WebApp 401: initData imzosi (HMAC) tasdiqlanmadi yoki 24 soatdan eski - "
                        "BOT_TOKEN noto'g'ri/mos kelmayotgan bo'lishi ham mumkin.")
        return None

    telegram_id = parsed["user"].get("id")
    if not telegram_id:
        logger.warning("WebApp 401: initData ichidagi 'user' obyektida 'id' topilmadi.")
        return None

    shop_id = await access_control.get_shop_id(telegram_id)
    if shop_id is None:
        logger.warning(
            f"WebApp 401: telegram_id={telegram_id} bazada na do'kon egasi, na sotuvchi "
            f"sifatida topildi (shop_id yo'q)."
        )
        return None

    # Faqat HAQIQIY do'kon egasi va sotuvchi savdo qila oladi (bosh admin emas) -
    # get_shop_id yuqorida allaqachon buni ta'minlaydi (adminga shop_id yo'q).
    role = await access_control.get_role(telegram_id)
    branch_id = await access_control.get_branch_id(telegram_id)
    access = await access_control.check_subscription_access(telegram_id)
    if not access.get("allowed"):
        logger.warning(
            f"WebApp 401: telegram_id={telegram_id} (shop_id={shop_id}) obunasi ruxsat "
            f"bermayapti - status={access.get('status')}."
        )
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
    payload = [_product_payload(p) for p in products]
    return web.json_response({"products": payload})


def _product_payload(p: dict) -> dict:
    """api_products va api_cross_sell bitta xil shakldagi mahsulot obyektini
    qaytarishi uchun umumiy funksiya - front-end (app.js) ikkalasini ham
    bitta renderProducts()/openAddModal() bilan ishlata oladi."""
    discount = db.product_discount_info(p)
    return {
        "id": p["id"],
        "name": p["name"],
        "quantity": p["quantity"],
        "price": p["price"],
        "sell_price": p.get("sell_price"),
        "min_price": p.get("min_price"),
        "discount_price": discount["price"] if discount else None,
        "discount_days_left": discount["days_left"] if discount else None,
        "barcode": p.get("barcode"),
    }


async def api_product_by_barcode(request: web.Request):
    """BARKOD - MINI APP SAVDO - 3-BOSQICH: kamera bilan o'qilgan barkod
    bo'yicha bitta mahsulotni topib qaytaradi (front-end shu javob asosida
    mahsulotni to'g'ridan-to'g'ri savatga qo'shadi - qo'lda qidirmasdan).

    Query param: code=<barkod matni>.

    DIQQAT: bu yerda mahsulot miqdori (quantity) tekshirilmaydi - 0 (yoki
    hatto manfiy) bo'lsa ham mahsulot o'zi topilgan bo'lsa qaytariladi,
    chunki front-end tarafda foydalanuvchiga "mahsulot topilmadi" bilan
    "mahsulot skladda tugagan"ni FARQLAB ko'rsatish kerak - buning uchun
    javobdagi "quantity" maydonidan foydalaniladi. Haqiqiy sklad
    tekshiruvi (savatga necha dona qo'shsa bo'ladi) baribir
    api_sale_submit'da yakuniy marta amalga oshiriladi."""
    auth = await _authenticate(request)
    if not auth:
        return web.json_response({"error": "unauthorized"}, status=401)

    barcode = request.query.get("code", "").strip()
    if not barcode:
        return web.json_response({"error": "missing_barcode"}, status=400)

    product = await db.find_product_by_barcode(auth["shop_id"], barcode)
    if not product:
        return web.json_response({"error": "not_found"}, status=404)

    return web.json_response({"product": _product_payload(product)})


async def api_cross_sell(request: web.Request):
    """3-BOSQICH: matnli oqimdagi "💡 Odatda bu tovar(lar) bilan birga
    quyidagilar ham sotib olinadi" taklifi bilan AYNAN BIR XIL
    db.get_cross_sell_suggestions() funksiyasidan foydalanadi - shu orqali
    veb-ilova va matnli oqim bir xil taklif mantig'iga ega bo'ladi.

    Query param: ids=1,2,3 - hozir savatdagi mahsulot id'lari (vergul bilan)."""
    auth = await _authenticate(request)
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


def _no_cache_file_response(path: Path) -> web.FileResponse:
    """DIQQAT (KESH MUAMMOSI TUZATILDI): Telegram Desktop/mobil webview
    statik fayllarni (index.html/app.js/style.css) juda qattiq keshlab
    qo'yadi - shu sababli kod yangilab deploy qilingandan keyin ham
    foydalanuvchida ESKI app.js ishlab qolishi mumkin edi (masalan initData
    tuzatishi kabi muhim javob bermay qolganday tuyulishi). Shu headerlar
    orqali brauzer/webview har safar serverdan yangi nusxa so'rashga
    majburlanadi."""
    resp = web.FileResponse(path)
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


_STARTUP_VERSION = str(int(time.time()))


async def webapp_index(request: web.Request):
    """"/webapp" VA "/webapp/" - ikkalasi ham index.html'ni qaytaradi.

    DIQQAT (403 XATOSI TUZATILDI): avval bu yerda aiohttp'ning add_static()
    ishlatilgan edi - lekin aiohttp static route DIREKTORIYA so'ralganda
    (masalan "/webapp/") ICHIDAGI index.html'ni O'ZI QIDIRIB TOPMAYDI va
    show_index=False bo'lgani uchun "403 Forbidden" qaytaradi. Shu sababli
    endi har bir fayl uchun ANIQ (aniq nomi bilan) route beriladi - hech
    qanday noaniqlik/403 xavfi qolmaydi.

    DIQQAT (KESH MUAMMOSI TUZATILDI): app.js/style.css havolalariga
    ?v=<botning ishga tushgan vaqti> qo'shiladi - shunda Telegram
    Desktop'ning o'zi Cache-Control'ni e'tiborsiz qoldirsa ham, deploydan
    keyin bu havolalar "yangi URL" bo'lib qoladi va eski keshlangan
    app.js/style.css o'rniga har doim yangisi yuklanadi."""
    html = (Path(config.WEBAPP_STATIC_DIR) / "index.html").read_text(encoding="utf-8")
    html = html.replace('href="/webapp/style.css"', f'href="/webapp/style.css?v={_STARTUP_VERSION}"')
    html = html.replace('src="/webapp/app.js"', f'src="/webapp/app.js?v={_STARTUP_VERSION}"')
    resp = web.Response(text=html, content_type="text/html")
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


async def webapp_app_js(request: web.Request):
    return _no_cache_file_response(Path(config.WEBAPP_STATIC_DIR) / "app.js")


async def webapp_style_css(request: web.Request):
    return _no_cache_file_response(Path(config.WEBAPP_STATIC_DIR) / "style.css")


def create_web_app(bot) -> web.Application:
    """Bitta aiohttp Application yaratadi - unga main.py kerak bo'lsa
    (WEBHOOK_HOST sozlangan bo'lsa) Telegram webhook route'ini ham
    qo'shib qo'yadi. Bu ilova PORT'da doim (polling bo'lsa ham) ishga
    tushiriladi - aks holda WebApp'ning HTTPS manzili ishlamay qoladi."""
    app = web.Application()
    app["bot"] = bot

    app.router.add_get("/api/webapp/me", api_me)
    app.router.add_get("/api/webapp/products", api_products)
    app.router.add_get("/api/webapp/products/by-barcode", api_product_by_barcode)
    app.router.add_get("/api/webapp/cross_sell", api_cross_sell)
    app.router.add_post("/api/webapp/sale", api_sale_submit)

    # MUHIM: har bir statik fayl uchun ANIQ route (yuqoridagi izohga qarang -
    # add_static() o'rniga, 403 Forbidden xatosining oldini olish uchun).
    # Yangi statik fayl (masalan rasm) qo'shilsa, shu yerga yana bitta
    # add_get qatori qo'shish kifoya.
    app.router.add_get("/webapp", webapp_index)
    app.router.add_get("/webapp/", webapp_index)
    app.router.add_get("/webapp/app.js", webapp_app_js)
    app.router.add_get("/webapp/style.css", webapp_style_css)

    async def health(request):
        return web.json_response({"status": "ok"})

    app.router.add_get("/health", health)

    return app
