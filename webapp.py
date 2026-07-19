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
from handlers.users import SETTING_LABELS, PRICE_SETTING_KEYS

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

    # 11-BOSQICH: BOSH ADMIN uchun alohida yo'l - uning shop_id'si yo'q
    # (do'kon boshqarmaydi, do'kon egalarini boshqaradi), shuning uchun
    # pastdagi shop_id/obuna tekshiruvidan OLDIN chiqib ketadi.
    if access_control.is_admin(telegram_id):
        return {
            "telegram_id": telegram_id,
            "shop_id": None,
            "role": "admin",
            "branch_id": None,
            "name": parsed["user"].get("first_name", ""),
        }

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
    # 11-BOSQICH: bosh adminning shop_id'si yo'q - can_add_stock so'rovi
    # (u shop_id'ga bog'liq) unga ma'nosiz, shuning uchun o'tkazib yuboriladi.
    if auth["role"] == "admin":
        return web.json_response({"name": auth["name"], "role": "admin", "can_add_stock": False})
    # 8-BOSQICH: front-end shu maydon orqali "📦 Sklad" bo'limidagi
    # "➕ Skladga qo'shish" imkoniyatini (yoki butun bo'limni) sotuvchidan
    # ega o'chirib qo'ygan bo'lsa yashiradi/qulflaydi - qarang: app.js init().
    can_add_stock = await access_control.can_add_stock(auth["telegram_id"])
    return web.json_response({
        "name": auth["name"],
        "role": auth["role"],
        "can_add_stock": can_add_stock,
    })


async def api_profile(request: web.Request):
    """PROFIL EKRANI: do'kon egasi va sotuvchi uchun "Admin panel"dagi kabi
    tartibli/chiroyli statistika+ma'lumot ekrani (qarang: webapp_static/app.js
    renderProfile()). Bosh adminga tegishli emas (u o'z "Admin panel"ida
    xuddi shunday ekranga ega - api_admin_stats)."""
    auth = await _authenticate(request)
    if not auth:
        return web.json_response({"error": "unauthorized"}, status=401)
    if auth["role"] == "admin":
        return web.json_response({"error": "not_applicable"}, status=404)

    shop_id = auth["shop_id"]
    owner = await db.get_owner(shop_id)
    access = await db.get_owner_subscription_access(shop_id) or {}
    branches = await db.get_branches(shop_id)
    sellers_can_add_stock = await db.get_sellers_can_add_stock(shop_id)

    payload = {
        "role": auth["role"],
        "telegram_id": auth["telegram_id"],
        "shop_name": (owner or {}).get("shop_name"),
        "status": access.get("status"),
        "days_left": access.get("days_left"),
        "subscription_until": (owner or {}).get("subscription_until"),
        "branches_count": len(branches),
        "sellers_can_add_stock": sellers_can_add_stock,
    }

    if auth["role"] == "owner":
        sellers = await db.get_sellers(shop_id)
        products = await db.get_all_products(shop_id)
        current_branch_id = (owner or {}).get("current_branch_id")
        current_branch = next((b for b in branches if b["id"] == current_branch_id), None)
        payload.update({
            "owner_name": (owner or {}).get("owner_name"),
            "phone_number": (owner or {}).get("phone_number"),
            "sellers_count": len(sellers),
            "products_count": len(products),
            "branch_name": current_branch["name"] if current_branch else "Bosh filial",
        })
    else:  # seller
        seller = await db.get_seller(auth["telegram_id"])
        branch_name = "Bosh filial"
        branch_id = (seller or {}).get("branch_id")
        if branch_id:
            match = next((b for b in branches if b["id"] == branch_id), None)
            if match:
                branch_name = match["name"]
        payload.update({
            "seller_name": (seller or {}).get("seller_name"),
            "phone_number": (seller or {}).get("phone_number"),
            "branch_name": branch_name,
            "can_add_stock": await access_control.can_add_stock(auth["telegram_id"]),
        })

    return web.json_response(payload)


async def api_branches_list(request: web.Request):
    """MINI APP ICHIDAN FILIALGA O'TISH: filiallar ro'yxati + joriy filial.
    Faqat HAQIQIY do'kon egasi uchun - sotuvchi o'z filialini o'zi
    almashtira olmaydi (qarang: access_control.get_branch_id izohi,
    handlers/branches.py bilan bir xil qoida)."""
    auth = await _authenticate(request)
    if not auth:
        return web.json_response({"error": "unauthorized"}, status=401)
    if auth["role"] != "owner":
        return web.json_response({"error": "not_applicable"}, status=404)

    shop_id = auth["shop_id"]
    owner = await db.get_owner(shop_id)
    branches = await db.get_branches(shop_id)
    current_branch_id = (owner or {}).get("current_branch_id")
    return web.json_response({
        "branches": [{"id": b["id"], "name": b["name"]} for b in branches],
        "current_branch_id": current_branch_id,
    })


async def api_branches_switch(request: web.Request):
    """handlers/branches.py'dagi branch_switch_cb bilan AYNAN BIR XIL amal -
    faqat mini app'dan chaqirilishi uchun. branch_id=null yuborilsa -
    "Bosh filial" (filialga bog'lanmagan holat)ga qaytaradi."""
    auth = await _authenticate(request)
    if not auth:
        return web.json_response({"error": "unauthorized"}, status=401)
    if auth["role"] != "owner":
        return web.json_response({"error": "not_applicable"}, status=404)

    shop_id = auth["shop_id"]
    try:
        body = await request.json()
    except Exception:
        body = {}
    branch_id = body.get("branch_id")

    branch_name = "Bosh filial"
    if branch_id is not None:
        branch = await db.get_branch(shop_id, int(branch_id))
        if not branch:
            return web.json_response({"error": "not_found"}, status=404)
        branch_name = branch["name"]
        branch_id = branch["id"]

    await db.set_owner_current_branch(shop_id, branch_id)
    return web.json_response({"ok": True, "branch_id": branch_id, "branch_name": branch_name})


async def api_sklad_permission_set(request: web.Request):
    """MINI APP ICHIDAN SKLAD RUXSATINI YOQISH/O'CHIRISH: handlers/sellers.py
    dagi sklad_permission_set_cb (bot'dagi "🔐 Sklad ruxsati") bilan AYNAN
    BIR XIL amal - faqat mini app Profil ekranidan chaqirilishi uchun.
    Faqat HAQIQIY do'kon egasi o'zgartira oladi."""
    auth = await _authenticate(request)
    if not auth:
        return web.json_response({"error": "unauthorized"}, status=401)
    if auth["role"] != "owner":
        return web.json_response({"error": "not_applicable"}, status=404)

    try:
        body = await request.json()
    except Exception:
        body = {}
    allowed = bool(body.get("allowed"))

    await db.set_sellers_can_add_stock(auth["shop_id"], allowed)
    return web.json_response({"ok": True, "allowed": allowed})


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
        "alert_quantity": p.get("alert_quantity"),
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
    api_sale_submit'da yakuniy marta amalga oshiriladi.

    ESLATMA: bu endpoint "Sklad" bo'limi (6-bosqich) uchun ham qayta
    ishlatiladi - u yerda ham 0 qolgan mahsulotni topa olish MUHIM
    (aynan shunday mahsulotlarga tovar kiritiladi), shuning uchun
    quantity>0 filtri bu yerda ham, u yerda ham qo'llanilmaydi."""
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


async def api_sklad_products(request: web.Request):
    """SKLAD - MINI APP - 6-BOSQICH: "Sklad" bo'limidagi qidiruv uchun
    mahsulotlar ro'yxati.

    DIQQAT: bu api_products'DAN FARQLI - u yerda faqat quantity>0 (SOTISH
    mumkin bo'lgan) mahsulotlar qaytariladi, bu yerda esa BARCHASI
    (shu jumladan 0 yoki hatto manfiy qolganlari ham) - chunki "Sklad"
    bo'limining aynan vazifasi TUGAGAN/kamayib qolgan mahsulotlarga
    tovar kiritish."""
    auth = await _authenticate(request)
    if not auth:
        return web.json_response({"error": "unauthorized"}, status=401)

    query = request.query.get("q", "").strip().lower()
    products = await db.get_all_products(auth["shop_id"])
    if query:
        # Kamera ishlamay qolsa ham (masalan kamera ruxsati berilmagan),
        # foydalanuvchi barkod raqamini qo'lda kiritib ham topa olishi
        # uchun - nomi YOKI barkodi bo'yicha qidiramiz.
        products = [
            p for p in products
            if query in p["name"].lower() or query in (p.get("barcode") or "").lower()
        ]
    payload = [_product_payload(p) for p in products]
    return web.json_response({"products": payload})


async def api_sklad_add_quantity(request: web.Request):
    """SKLAD - MINI APP - 6-BOSQICH: mahsulotga tez miqdor qo'shadi
    (narx so'ramaydi - shu bilan restock/xarid oqimidan farq qiladi,
    qarang: db.add_stock_quantity() izohi).

    Body (JSON): {"product_id": .. } YOKI {"barcode": ".."} (ikkalasidan
    KAMIDA bittasi kerak - front-end skanerlagan bo'lsa barcode, ro'yxatdan
    qidirib tanlagan bo'lsa product_id yuboradi), va {"qty": son (musbat)}.

    RUXSAT (8-BOSQICH): do'kon egasi har doim qo'sha oladi. Sotuvchi esa
    faqat ega buni yoqib qo'ygan bo'lsa (owners.sellers_can_add_stock,
    standart - yoqilgan) - qarang: access_control.can_add_stock() va
    handlers/sellers.py ("🔐 Sklad ruxsati" tugmasi)."""
    auth = await _authenticate(request)
    if not auth:
        return web.json_response({"error": "unauthorized"}, status=401)

    if not await access_control.can_add_stock(auth["telegram_id"]):
        return web.json_response({"error": "forbidden"}, status=403)

    try:
        body = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "invalid_json"}, status=400)

    try:
        qty = float(body.get("qty"))
    except (TypeError, ValueError):
        return web.json_response({"error": "invalid_quantity"}, status=400)
    if qty <= 0:
        return web.json_response({"error": "invalid_quantity"}, status=400)

    shop_id = auth["shop_id"]
    product = None

    raw_product_id = body.get("product_id")
    if raw_product_id is not None:
        try:
            product_id = int(raw_product_id)
        except (TypeError, ValueError):
            return web.json_response({"error": "invalid_item"}, status=400)
        product = await db.get_product(shop_id, product_id)
    else:
        barcode = (body.get("barcode") or "").strip()
        if not barcode:
            return web.json_response({"error": "missing_product"}, status=400)
        product = await db.find_product_by_barcode(shop_id, barcode)

    if not product:
        return web.json_response({"error": "product_not_found"}, status=400)

    result = await db.add_stock_quantity(shop_id, product["id"], qty, performed_by=auth["telegram_id"])
    if not result:
        return web.json_response({"error": "product_not_found"}, status=400)

    return web.json_response({
        "ok": True,
        "product_id": product["id"],
        "name": result["name"],
        "old_quantity": result["old_quantity"],
        "new_quantity": result["new_quantity"],
    })


async def api_sklad_create_product(request: web.Request):
    """SKLAD - MINI APP - YANGI REJA (10-BOSQICHLI) - 1-BOSQICH: "Sklad"
    bo'limida to'g'ridan-to'g'ri (Telegram matnli oqimiga chiqmasdan)
    YANGI mahsulot yaratish uchun backend qismi.

    Bu - butun rejaning FAQAT birinchi bosqichi: hozircha faqat backend
    (API + validatsiya) tayyor - front-end tugma/forma keyingi
    bosqichlarda (2-4) qo'shiladi. Barkod skanerlash orqali to'ldirish
    (5-bosqich) va savdo oqimidagi o'zgarish (6-7-bosqich) ham keyinroq.

    Body (JSON):
      - "name": mahsulot nomi (majburiy, bo'sh bo'lmasin)
      - "price": tannarx (majburiy, >= 0)
      - "sell_price": sotish narxi (ixtiyoriy)
      - "quantity": boshlang'ich miqdor (majburiy, >= 0)
      - "barcode": barkod matni (ixtiyoriy - qo'lda kiritilgan yoki
        keyingi bosqichda kamera bilan skanerlangan bo'lishi mumkin)

    RUXSAT: xuddi api_sklad_add_quantity bilan bir xil - faqat
    access_control.can_add_stock() ruxsat bergan foydalanuvchi (do'kon
    egasi doim, sotuvchi esa ega yoqib qo'ygan bo'lsa) yangi mahsulot
    qo'sha oladi.

    DIQQAT (BARKOD TAKRORLANISHI): agar yuborilgan barkod shu do'konda
    ALLAQACHON boshqa mahsulotga biriktirilgan bo'lsa, yangi mahsulot
    YARATILMAYDI - o'rniga "barcode_exists" xatosi va mavjud mahsulot
    ma'lumoti qaytariladi. Buning sababi: bitta barkod ikkita xil
    mahsulotga tegishli bo'lib qolsa, keyinchalik savdoda/skladda shu
    barkod skanerlanganda QAYSI mahsulot nazarda tutilgani noaniq
    bo'lib qoladi. Front-end (keyingi bosqichda) bu xatoni ko'rib,
    foydalanuvchiga "bu barkod allaqachon <mahsulot nomi>da bor - unga
    miqdor qo'shilsinmi?" kabi tanlov taklif qilishi mumkin."""
    auth = await _authenticate(request)
    if not auth:
        return web.json_response({"error": "unauthorized"}, status=401)

    if not await access_control.can_add_stock(auth["telegram_id"]):
        return web.json_response({"error": "forbidden"}, status=403)

    try:
        body = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "invalid_json"}, status=400)

    name = (body.get("name") or "").strip()
    if not name:
        return web.json_response({"error": "missing_name"}, status=400)

    try:
        price = float(body.get("price"))
    except (TypeError, ValueError):
        return web.json_response({"error": "invalid_price"}, status=400)
    if price < 0:
        return web.json_response({"error": "invalid_price"}, status=400)

    sell_price = None
    if body.get("sell_price") not in (None, ""):
        try:
            sell_price = float(body.get("sell_price"))
        except (TypeError, ValueError):
            return web.json_response({"error": "invalid_sell_price"}, status=400)
        if sell_price < 0:
            return web.json_response({"error": "invalid_sell_price"}, status=400)

    min_price = None
    if body.get("min_price") not in (None, ""):
        try:
            min_price = float(body.get("min_price"))
        except (TypeError, ValueError):
            return web.json_response({"error": "invalid_min_price"}, status=400)
        if min_price < 0:
            return web.json_response({"error": "invalid_min_price"}, status=400)

    try:
        quantity = float(body.get("quantity"))
    except (TypeError, ValueError):
        return web.json_response({"error": "invalid_quantity"}, status=400)
    if quantity < 0:
        return web.json_response({"error": "invalid_quantity"}, status=400)

    alert_quantity = None
    if body.get("alert_quantity") not in (None, ""):
        try:
            alert_quantity = float(body.get("alert_quantity"))
        except (TypeError, ValueError):
            return web.json_response({"error": "invalid_alert_quantity"}, status=400)
        if alert_quantity < 0:
            return web.json_response({"error": "invalid_alert_quantity"}, status=400)

    barcode = (body.get("barcode") or "").strip() or None

    shop_id = auth["shop_id"]

    if barcode:
        existing = await db.find_product_by_barcode(shop_id, barcode)
        if existing:
            return web.json_response({
                "error": "barcode_exists",
                "product": _product_payload(existing),
            }, status=409)

    product_id = await db.add_product(
        shop_id, name, price, quantity, None,
        sell_price=sell_price, min_price=min_price, alert_quantity=alert_quantity, barcode=barcode,
    )

    try:
        await db.log_action(
            shop_id, auth["telegram_id"], "Veb-ilova orqali yangi mahsulot qo'shildi",
            f"{name} — {quantity:.0f} dona" + (f", barkod: {barcode}" if barcode else ""),
        )
    except Exception:
        logger.warning("WebApp yangi mahsulot log_action xatosi", exc_info=True)

    product = await db.get_product(shop_id, product_id)
    return web.json_response({"ok": True, "product": _product_payload(product)})


async def api_sklad_update_product(request: web.Request):
    """7-BOSQICH: Sklad bo'limidan mavjud mahsulotni tahrirlash (nomi,
    tannarxi, sotish narxi, eng past narxi, barkodi).

    RUXSAT: FAQAT do'kon egasi (is_owner_level) - narx/tannarxni
    o'zgartirish sotuvchiga berilgan "sklad ruxsati"dan (can_add_stock,
    faqat miqdor qo'shish uchun) FARQLI, jiddiyroq huquq, shuning uchun
    bu yerda alohida (qattiqroq) tekshiruv qilinadi.

    Body (JSON): {"product_id": .., "name": .. (ixtiyoriy),
    "price": .. (ixtiyoriy), "sell_price": .. (ixtiyoriy, "" bo'lsa olib
    tashlanadi), "min_price": .. (ixtiyoriy, "" bo'lsa olib tashlanadi),
    "barcode": .. (ixtiyoriy, "" bo'lsa olib tashlanadi)}.
    Faqat body'da KELGAN maydonlar yangilanadi - kelmagan maydonlarga
    tegilmaydi."""
    auth = await _authenticate(request)
    if not auth:
        return web.json_response({"error": "unauthorized"}, status=401)

    if not await access_control.is_owner_level(auth["telegram_id"]):
        return web.json_response({"error": "forbidden"}, status=403)

    try:
        body = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "invalid_json"}, status=400)

    shop_id = auth["shop_id"]

    try:
        product_id = int(body.get("product_id"))
    except (TypeError, ValueError):
        return web.json_response({"error": "invalid_item"}, status=400)

    product = await db.get_product(shop_id, product_id)
    if not product:
        return web.json_response({"error": "product_not_found"}, status=400)

    if "name" in body:
        name = (body.get("name") or "").strip()
        if not name:
            return web.json_response({"error": "missing_name"}, status=400)
        await db.rename_product(shop_id, product_id, name)

    if "price" in body:
        try:
            price = float(body.get("price"))
        except (TypeError, ValueError):
            return web.json_response({"error": "invalid_price"}, status=400)
        if price < 0:
            return web.json_response({"error": "invalid_price"}, status=400)
        await db.update_product_field(shop_id, product_id, "price", price)

    if "sell_price" in body:
        raw = body.get("sell_price")
        if raw in (None, ""):
            await db.update_product_field(shop_id, product_id, "sell_price", None)
        else:
            try:
                sell_price = float(raw)
            except (TypeError, ValueError):
                return web.json_response({"error": "invalid_sell_price"}, status=400)
            if sell_price < 0:
                return web.json_response({"error": "invalid_sell_price"}, status=400)
            await db.update_product_field(shop_id, product_id, "sell_price", sell_price)

    if "min_price" in body:
        raw = body.get("min_price")
        if raw in (None, ""):
            await db.update_product_field(shop_id, product_id, "min_price", None)
        else:
            try:
                min_price = float(raw)
            except (TypeError, ValueError):
                return web.json_response({"error": "invalid_min_price"}, status=400)
            if min_price < 0:
                return web.json_response({"error": "invalid_min_price"}, status=400)
            await db.update_product_field(shop_id, product_id, "min_price", min_price)

    if "alert_quantity" in body:
        raw = body.get("alert_quantity")
        if raw in (None, ""):
            await db.update_product_field(shop_id, product_id, "alert_quantity", None)
        else:
            try:
                alert_quantity = float(raw)
            except (TypeError, ValueError):
                return web.json_response({"error": "invalid_alert_quantity"}, status=400)
            if alert_quantity < 0:
                return web.json_response({"error": "invalid_alert_quantity"}, status=400)
            await db.update_product_field(shop_id, product_id, "alert_quantity", alert_quantity)

    if "barcode" in body:
        barcode = (body.get("barcode") or "").strip() or None
        if barcode:
            existing = await db.find_product_by_barcode(shop_id, barcode)
            if existing and existing["id"] != product_id:
                return web.json_response({
                    "error": "barcode_exists", "product": _product_payload(existing),
                }, status=409)
        await db.set_product_barcode(shop_id, product_id, barcode, performed_by=auth["telegram_id"])

    updated = await db.get_product(shop_id, product_id)
    return web.json_response({"ok": True, "product": _product_payload(updated)})


# 9-BOSQICH: SKLAD TARIXI - audit_log jadvalidagi barcha amal turlaridan
# faqat SKLAD/MAHSULOT bilan bog'liqlarini ko'rsatamiz - "Kirim"/"Chiqim"
# (pul harakati) va "Savdo bekor qilindi" kabi boshqa bo'limlarga tegishli
# yozuvlar bu yerda ortiqcha shovqin bo'lardi (ular allaqachon "Hisobot"
# bo'limida bor).
_SKLAD_HISTORY_ACTIONS = {
    "Skladga tovar qo'shildi (Mini App)",
    "Sklad to'ldirildi (qayta xarid)",
    "Veb-ilova orqali yangi mahsulot qo'shildi",
    "Excel orqali sklad to'ldirildi",
    "Mahsulot o'chirildi",
    "Barkod belgilandi",
    "Barkod o'zgartirildi",
}


async def api_sklad_history(request: web.Request):
    auth = await _authenticate(request)
    if not auth:
        return web.json_response({"error": "unauthorized"}, status=401)

    # audit_log'dan kengroq oyna olib (200 ta), keyin faqat sklad turlarini
    # filtrlab, oxirgi 50 tasini qaytaramiz - shu orqali oraga ko'p sonli
    # "Kirim"/"Chiqim" yozuvlari tushib qolgan taqdirda ham sklad tarixi
    # "qisqarib" qolmaydi.
    rows = await db.get_audit_log(auth["shop_id"], limit=200)
    sklad_rows = [r for r in rows if r["action"] in _SKLAD_HISTORY_ACTIONS][:50]
    payload = [
        {
            "action": r["action"],
            "details": r["details"],
            "actor_name": r["actor_name"],
            "created_at": r["created_at"],
        }
        for r in sklad_rows
    ]
    return web.json_response({"history": payload})


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


# =====================================================================
# 11-BOSQICH: BOSH ADMIN PANELI - MINI APP
# =====================================================================
# Ilgari bosh admin ("do'kon egalarini boshqarish, obuna, to'lovlar,
# adminlar, ommaviy xabar) FAQAT botning matnli menyusi orqali ishlagan
# (handlers/users.py, handlers/subscription.py). Endi shu FUNKSIYALARNING
# HAMMASI mini appda ham (yangi "🛠 Admin" ekrani) ishlaydi - matnli menyu
# HECH QAERDA o'chirilmadi, ikkalasi PARALLEL ishlaydi.
#
# Pastdagi funksiyalar business-mantiqni QAYTA YOZMAYDI - ular
# database.py/access_control.py'dagi bot handlerlari ishlatgan XUDDI O'SHA
# funksiyalarni chaqiradi, faqat natijani Telegram xabari o'rniga JSON
# qilib qaytaradi. Shu sababli bot orqali va mini app orqali qilingan
# amallar bir-biriga to'liq mos (masalan botdan bloklangan ega mini
# appda ham bloklangan ko'rinadi va aksincha).

async def _require_admin(request: web.Request):
    """Barcha /api/webapp/admin/* endpointlar uchun umumiy tekshiruv.

    Muvaffaqiyatli bo'lsa (auth_dict, None) qaytaradi. Muvaffaqiyatsiz
    bo'lsa (None, tayyor_javob) qaytaradi - chaqiruvchi shunchaki
    ``if err: return err`` qilishi kifoya, har bir endpointda 401/403'ni
    alohida yozish shart emas."""
    auth = await _authenticate(request)
    if not auth:
        return None, web.json_response({"error": "unauthorized"}, status=401)
    if auth["role"] != "admin":
        return None, web.json_response({"error": "forbidden"}, status=403)
    return auth, None


def _owner_payload(o: dict, access: dict | None) -> dict:
    """Bitta do'kon egasi haqidagi ma'lumotni front-end kutgan shaklda
    (JSON) qaytaradi - handlers/users.py'dagi _owner_card_text() bilan
    bir xil ma'lumotlar, faqat matn emas, alohida maydonlar sifatida."""
    return {
        "telegram_id": o["telegram_id"],
        "owner_name": o.get("owner_name"),
        "shop_name": o.get("shop_name"),
        "phone_number": o.get("phone_number"),
        "full_name": o.get("full_name"),
        "username": o.get("username"),
        "status": (access or {}).get("status"),
        "days_left": (access or {}).get("days_left"),
        "blocked": bool(access and access.get("status") == "blocked"),
        "subscription_until": o.get("subscription_until"),
    }


async def api_admin_stats(request: web.Request):
    """Admin ekranining tepasidagi qisqacha statistika kartochkalari uchun."""
    auth, err = await _require_admin(request)
    if err:
        return err

    owners = await db.get_owners()
    sellers = await db.get_all_sellers()
    payments = await db.get_pending_payments()
    admins = await db.get_admins()

    blocked_count = 0
    for o in owners:
        access = await access_control.check_subscription_access(o["telegram_id"])
        if access and access.get("status") == "blocked":
            blocked_count += 1

    return web.json_response({
        "owners_count": len(owners),
        "sellers_count": len(sellers),
        "blocked_count": blocked_count,
        "pending_payments_count": len(payments),
        "extra_admins_count": len(admins),
    })


async def api_admin_owners_list(request: web.Request):
    """Do'kon egalari ro'yxati, ixtiyoriy ``q`` (qidiruv) parametri bilan -
    ism, do'kon nomi, telefon yoki telegram_id bo'yicha qidiradi."""
    auth, err = await _require_admin(request)
    if err:
        return err

    q = (request.query.get("q") or "").strip().lower()
    owners = await db.get_owners()
    result = []
    for o in owners:
        if q:
            haystack = " ".join(
                str(o.get(k) or "")
                for k in ("owner_name", "shop_name", "phone_number", "full_name", "username")
            ) + " " + str(o["telegram_id"])
            if q not in haystack.lower():
                continue
        access = await access_control.check_subscription_access(o["telegram_id"])
        result.append(_owner_payload(o, access))
    return web.json_response({"owners": result})


async def api_admin_owner_detail(request: web.Request):
    auth, err = await _require_admin(request)
    if err:
        return err
    target_id = int(request.match_info["owner_id"])
    owner = await db.get_owner(target_id)
    if not owner:
        return web.json_response({"error": "not_found"}, status=404)
    access = await access_control.check_subscription_access(target_id)
    return web.json_response({"owner": _owner_payload(owner, access)})


async def api_admin_owner_add(request: web.Request):
    """Yangi do'kon egasini telegram_id orqali qo'shadi (mini appda xabar
    forward qilib bo'lmaydi, shuning uchun FAQAT ID orqali - taklif linki
    kerak bo'lsa api_admin_owner_invite_link ishlatiladi)."""
    auth, err = await _require_admin(request)
    if err:
        return err
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "invalid_json"}, status=400)
    try:
        target_id = int(str(body.get("telegram_id")).strip())
    except (TypeError, ValueError):
        return web.json_response({"error": "invalid_telegram_id"}, status=400)

    if access_control.is_admin(target_id):
        return web.json_response({"error": "already_admin"}, status=409)
    if await db.is_owner(target_id):
        return web.json_response({"error": "already_owner"}, status=409)

    await db.add_owner(target_id, None, None, added_by=auth["telegram_id"])

    bot = request.app["bot"]
    try:
        await bot.send_message(
            target_id,
            "✅ Sizga do'kon boshqaruv botidan foydalanish huquqi berildi.\n"
            "Boshlash uchun /start buyrug'ini bosing.",
        )
    except Exception:
        pass

    owner = await db.get_owner(target_id)
    access = await access_control.check_subscription_access(target_id)
    return web.json_response({"owner": _owner_payload(owner, access)})


async def api_admin_owner_invite_link(request: web.Request):
    auth, err = await _require_admin(request)
    if err:
        return err
    token = await db.create_owner_invite(auth["telegram_id"])
    bot = request.app["bot"]
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=owner_{token}"
    return web.json_response({"link": link})


async def api_admin_owner_remove(request: web.Request):
    auth, err = await _require_admin(request)
    if err:
        return err
    target_id = int(request.match_info["owner_id"])
    removed = await db.remove_owner(target_id)
    if not removed:
        return web.json_response({"error": "not_found"}, status=404)
    return web.json_response({"ok": True})


async def api_admin_owner_extend(request: web.Request):
    auth, err = await _require_admin(request)
    if err:
        return err
    target_id = int(request.match_info["owner_id"])
    try:
        body = await request.json()
        days = int(body.get("days"))
    except (json.JSONDecodeError, TypeError, ValueError):
        return web.json_response({"error": "invalid_days"}, status=400)
    if days == 0:
        return web.json_response({"error": "invalid_days"}, status=400)

    new_until = await db.extend_owner_subscription(target_id, days)
    if new_until is None:
        return web.json_response({"error": "not_found"}, status=404)

    bot = request.app["bot"]
    if days >= 0:
        note = f"✅ Bosh admin obunangizni qo'lda {days} kunga uzaytirdi."
    else:
        note = f"⚠️ Bosh admin obunangizni qo'lda {abs(days)} kunga qisqartirdi."
    try:
        await bot.send_message(target_id, f"{note}\n📅 Endi {new_until} sanagacha amal qiladi.")
    except Exception:
        pass

    owner = await db.get_owner(target_id)
    access = await access_control.check_subscription_access(target_id)
    return web.json_response({"owner": _owner_payload(owner, access)})


async def api_admin_owner_block(request: web.Request):
    auth, err = await _require_admin(request)
    if err:
        return err
    target_id = int(request.match_info["owner_id"])
    ok = await db.set_owner_blocked(target_id, True)
    if not ok:
        return web.json_response({"error": "not_found"}, status=404)

    bot = request.app["bot"]
    try:
        await bot.send_message(
            target_id,
            "⛔ Bosh admin sizning obunangizni majburan bloklandi. "
            "Savolingiz bo'lsa, bosh admin bilan bog'laning.",
        )
    except Exception:
        pass

    owner = await db.get_owner(target_id)
    access = await access_control.check_subscription_access(target_id)
    return web.json_response({"owner": _owner_payload(owner, access)})


async def api_admin_owner_unblock(request: web.Request):
    auth, err = await _require_admin(request)
    if err:
        return err
    target_id = int(request.match_info["owner_id"])
    ok = await db.set_owner_blocked(target_id, False)
    if not ok:
        return web.json_response({"error": "not_found"}, status=404)

    bot = request.app["bot"]
    try:
        await bot.send_message(
            target_id,
            "✅ Bosh admin sizning blokingizni bekor qildi. Obunangiz oldingi holatiga qaytdi.",
        )
    except Exception:
        pass

    owner = await db.get_owner(target_id)
    access = await access_control.check_subscription_access(target_id)
    return web.json_response({"owner": _owner_payload(owner, access)})


async def api_admin_admins_list(request: web.Request):
    auth, err = await _require_admin(request)
    if err:
        return err
    db_admins = await db.get_admins()
    return web.json_response({
        "env_admin_ids": list(config.ADMIN_IDS),
        "admins": [
            {
                "telegram_id": a["telegram_id"],
                "full_name": a.get("full_name"),
                "username": a.get("username"),
            }
            for a in db_admins
        ],
    })


async def api_admin_admins_add(request: web.Request):
    """Yangi BOSH ADMIN qo'shadi - handlers/users.py'dagi add_admin_finish
    bilan bir xil tekshiruvlar (allaqachon admin/owner/seller bo'lmasligi)."""
    auth, err = await _require_admin(request)
    if err:
        return err
    try:
        body = await request.json()
        target_id = int(str(body.get("telegram_id")).strip())
    except (json.JSONDecodeError, TypeError, ValueError):
        return web.json_response({"error": "invalid_telegram_id"}, status=400)

    if access_control.is_admin(target_id):
        return web.json_response({"error": "already_admin"}, status=409)
    if await db.is_owner(target_id):
        return web.json_response({"error": "is_owner"}, status=409)
    if await db.is_seller(target_id):
        return web.json_response({"error": "is_seller"}, status=409)

    await db.add_admin(target_id, None, None, added_by=auth["telegram_id"])
    access_control.register_extra_admin(target_id)

    bot = request.app["bot"]
    try:
        await bot.send_message(
            target_id,
            "👑 Sizga botda BOSH ADMIN huquqi berildi.\nBoshlash uchun /start buyrug'ini bosing.",
        )
    except Exception:
        pass

    return web.json_response({"ok": True})


async def api_admin_admins_remove(request: web.Request):
    auth, err = await _require_admin(request)
    if err:
        return err
    target_id = int(request.match_info["admin_id"])
    if target_id == auth["telegram_id"]:
        return web.json_response({"error": "cannot_remove_self"}, status=400)
    removed = await db.remove_admin(target_id)
    if not removed:
        return web.json_response({
            "error": "not_found",
            "message": "Bu odam .env orqali qo'shilgan bo'lishi mumkin - u faqat .env orqali olib tashlanadi.",
        }, status=404)
    access_control._extra_admin_ids.discard(target_id)
    return web.json_response({"ok": True})


async def api_admin_admins_invite_link(request: web.Request):
    auth, err = await _require_admin(request)
    if err:
        return err
    token = await db.create_admin_invite(auth["telegram_id"])
    bot = request.app["bot"]
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=admin_{token}"
    return web.json_response({"link": link})


async def _payment_payload(p: dict) -> dict:
    owner = await db.get_owner(p["owner_id"])
    owner_label = (
        (owner or {}).get("shop_name")
        or (owner or {}).get("owner_name")
        or (owner or {}).get("full_name")
        or str(p["owner_id"])
    )
    plan = config.SUBSCRIPTION_PLANS.get(p.get("plan"), {})
    return {
        "id": p["id"],
        "owner_id": p["owner_id"],
        "owner_label": owner_label,
        "plan_label": plan.get("label", p.get("plan") or "erkin"),
        "amount": p["amount"],
        "days": p.get("days") or 0,
        "created_at": p["created_at"],
        "has_photo": bool(p.get("screenshot_file_id")),
    }


async def api_admin_payments_list(request: web.Request):
    auth, err = await _require_admin(request)
    if err:
        return err
    payments = await db.get_pending_payments()
    payload = [await _payment_payload(p) for p in payments]
    return web.json_response({"payments": payload})


async def api_admin_payment_photo(request: web.Request):
    """To'lov cheki skrinshotini Telegram serveridan olib, to'g'ridan-to'g'ri
    rasm sifatida qaytaradi (mini app <img> tegida ko'rsatishi uchun)."""
    auth, err = await _require_admin(request)
    if err:
        return err
    payment_id = int(request.match_info["payment_id"])
    payment = await db.get_payment(payment_id)
    if not payment or not payment.get("screenshot_file_id"):
        return web.json_response({"error": "not_found"}, status=404)

    bot = request.app["bot"]
    try:
        tg_file = await bot.get_file(payment["screenshot_file_id"])
        buf = await bot.download_file(tg_file.file_path)
        data = buf.read()
    except Exception:
        return web.json_response({"error": "fetch_failed"}, status=502)

    resp = web.Response(body=data, content_type="image/jpeg")
    resp.headers["Cache-Control"] = "private, max-age=3600"
    return resp


async def api_admin_payment_approve(request: web.Request):
    auth, err = await _require_admin(request)
    if err:
        return err
    payment_id = int(request.match_info["payment_id"])
    result = await db.approve_payment(payment_id, decided_by=auth["telegram_id"])
    if not result:
        return web.json_response({"error": "already_decided"}, status=409)

    plan = config.SUBSCRIPTION_PLANS.get(result.get("plan"), {})
    plan_label = plan.get("label", result.get("plan") or "")
    bot = request.app["bot"]
    try:
        await bot.send_message(
            result["owner_id"],
            f"✅ To'lovingiz tasdiqlandi! Tarif: {plan_label}.\n"
            f"📅 Obunangiz {result['new_subscription_until']} sanagacha uzaytirildi. Rahmat!",
        )
    except Exception:
        pass
    return web.json_response({"ok": True})


async def api_admin_payment_reject(request: web.Request):
    auth, err = await _require_admin(request)
    if err:
        return err
    payment_id = int(request.match_info["payment_id"])
    result = await db.reject_payment(payment_id, decided_by=auth["telegram_id"])
    if not result:
        return web.json_response({"error": "already_decided"}, status=409)

    bot = request.app["bot"]
    try:
        await bot.send_message(
            result["owner_id"],
            "❌ Yuborgan chekingiz rad etildi (noto'g'ri yoki noaniq bo'lishi mumkin). "
            "Iltimos, to'lovni tekshirib, chekni qaytadan yuboring: \"💳 Obuna\" bo'limidan.",
        )
    except Exception:
        pass
    return web.json_response({"ok": True})


async def api_admin_settings_get(request: web.Request):
    auth, err = await _require_admin(request)
    if err:
        return err
    plans = await db.get_subscription_plans()
    requisites = await db.get_payment_requisites()
    return web.json_response({"plans": plans, "requisites": requisites})


async def api_admin_settings_update(request: web.Request):
    """handlers/users.py'dagi edit_setting_finish() bilan bir xil
    tekshiruvlar: narx maydonlari (price_1m/3m/12m) uchun musbat butun son,
    boshqalari (karta raqami va h.k.) uchun bo'sh bo'lmagan matn."""
    auth, err = await _require_admin(request)
    if err:
        return err
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "invalid_json"}, status=400)

    key = (body.get("key") or "").strip()
    label = SETTING_LABELS.get(key)
    if not label:
        return web.json_response({"error": "invalid_key"}, status=400)

    value_raw = str(body.get("value") if body.get("value") is not None else "").strip()
    if key in PRICE_SETTING_KEYS:
        if not value_raw.isdigit() or int(value_raw) <= 0:
            return web.json_response({"error": "invalid_value"}, status=400)
        value = str(int(value_raw))
    else:
        if not value_raw:
            return web.json_response({"error": "invalid_value"}, status=400)
        value = value_raw

    await db.set_setting(key, value)
    plans = await db.get_subscription_plans()
    requisites = await db.get_payment_requisites()
    return web.json_response({"plans": plans, "requisites": requisites})


async def api_admin_broadcast(request: web.Request):
    auth, err = await _require_admin(request)
    if err:
        return err
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "invalid_json"}, status=400)

    text = (body.get("text") or "").strip()
    if not text:
        return web.json_response({"error": "empty_text"}, status=400)

    owners = await db.get_owners()
    sellers = await db.get_all_sellers()
    recipient_ids = {o["telegram_id"] for o in owners} | {s["telegram_id"] for s in sellers}

    bot = request.app["bot"]
    sent, failed = 0, 0
    for telegram_id in recipient_ids:
        try:
            await bot.send_message(telegram_id, f"📢 <b>E'lon</b>\n\n{text}", parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1

    return web.json_response({"sent": sent, "failed": failed, "total": len(recipient_ids)})


def create_web_app(bot) -> web.Application:

    """Bitta aiohttp Application yaratadi - unga main.py kerak bo'lsa
    (WEBHOOK_HOST sozlangan bo'lsa) Telegram webhook route'ini ham
    qo'shib qo'yadi. Bu ilova PORT'da doim (polling bo'lsa ham) ishga
    tushiriladi - aks holda WebApp'ning HTTPS manzili ishlamay qoladi."""
    app = web.Application()
    app["bot"] = bot

    app.router.add_get("/api/webapp/me", api_me)
    app.router.add_get("/api/webapp/profile", api_profile)
    app.router.add_get("/api/webapp/branches", api_branches_list)
    app.router.add_post("/api/webapp/branches/switch", api_branches_switch)
    app.router.add_post("/api/webapp/sklad-permission", api_sklad_permission_set)
    app.router.add_get("/api/webapp/products", api_products)
    app.router.add_get("/api/webapp/products/by-barcode", api_product_by_barcode)
    app.router.add_get("/api/webapp/cross_sell", api_cross_sell)
    app.router.add_post("/api/webapp/sale", api_sale_submit)
    app.router.add_get("/api/webapp/sklad/products", api_sklad_products)
    app.router.add_post("/api/webapp/sklad/add-quantity", api_sklad_add_quantity)
    app.router.add_post("/api/webapp/sklad/create-product", api_sklad_create_product)
    app.router.add_post("/api/webapp/sklad/update-product", api_sklad_update_product)
    app.router.add_get("/api/webapp/sklad/history", api_sklad_history)

    # 11-BOSQICH: BOSH ADMIN PANELI (mini app)
    app.router.add_get("/api/webapp/admin/stats", api_admin_stats)
    app.router.add_get("/api/webapp/admin/owners", api_admin_owners_list)
    app.router.add_post("/api/webapp/admin/owners", api_admin_owner_add)
    app.router.add_get("/api/webapp/admin/owners/invite-link", api_admin_owner_invite_link)
    app.router.add_get("/api/webapp/admin/owners/{owner_id}", api_admin_owner_detail)
    app.router.add_delete("/api/webapp/admin/owners/{owner_id}", api_admin_owner_remove)
    app.router.add_post("/api/webapp/admin/owners/{owner_id}/extend", api_admin_owner_extend)
    app.router.add_post("/api/webapp/admin/owners/{owner_id}/block", api_admin_owner_block)
    app.router.add_post("/api/webapp/admin/owners/{owner_id}/unblock", api_admin_owner_unblock)
    app.router.add_get("/api/webapp/admin/admins", api_admin_admins_list)
    app.router.add_post("/api/webapp/admin/admins", api_admin_admins_add)
    app.router.add_get("/api/webapp/admin/admins/invite-link", api_admin_admins_invite_link)
    app.router.add_delete("/api/webapp/admin/admins/{admin_id}", api_admin_admins_remove)
    app.router.add_get("/api/webapp/admin/payments", api_admin_payments_list)
    app.router.add_get("/api/webapp/admin/payments/{payment_id}/photo", api_admin_payment_photo)
    app.router.add_post("/api/webapp/admin/payments/{payment_id}/approve", api_admin_payment_approve)
    app.router.add_post("/api/webapp/admin/payments/{payment_id}/reject", api_admin_payment_reject)
    app.router.add_get("/api/webapp/admin/settings", api_admin_settings_get)
    app.router.add_post("/api/webapp/admin/settings", api_admin_settings_update)
    app.router.add_post("/api/webapp/admin/broadcast", api_admin_broadcast)

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
