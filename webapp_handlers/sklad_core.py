"""SKLAD - MAHSULOTLAR YADROSI - MINI APP (20-BOSQICH: REFAKTORING).

Bu modul ilgari webapp.py ichida to'g'ridan-to'g'ri yozilgan edi (6-BOSQICH
va keyingi bosqichlarda qo'shilgan). 20-bosqichda webapp.py'ni "barcha
routerlarni yig'uvchi asosiy fayl"ga aylantirish maqsadida BU YERGA
ko'chirildi - XATTI-HARAKAT (route manzillari, biznes mantiq, xatoliklar)
BUTUNLAY O'ZGARMADI, faqat joyi o'zgardi.

Bu yerda: mahsulotlar ro'yxati (Savdo va Sklad bo'limlari uchun umumiy),
barkod bo'yicha qidirish, Sklad bo'limidagi tez miqdor qo'shish/yangi
mahsulot yaratish/tahrirlash/tarix, va "Olinishi kerak bo'lgan tovarlar"
ro'yxati.

MUHIM - BIR XILLIK: handlers/sales.py va handlers/products.py (bot
tarafi)dagi bilan AYNAN BIR XIL database.py funksiyalaridan foydalanadi.

DIQQAT - AYLANMA IMPORT: bu modul _authenticate'ni webapp.py'dan LOKAL
(funksiya ichida) import qiladi - webapp.py'ning o'zi bu modulni
create_web_app() ichida import qilgani uchun, modul darajasidagi
("yuqorida") import aylanma bo'lardi.
"""

import json
import logging
from pathlib import Path

from aiohttp import web

import config
import database as db
import access_control
from handlers.sales import _sellable_products

logger = logging.getLogger(__name__)


async def _require_auth(request: web.Request):
    """webapp._authenticate orqali autentifikatsiya qiladi. Aylanma import
    (webapp.py <-> webapp_handlers/sklad_core.py)dan qochish uchun import
    shu yerda (funksiya ichida) - xavfsiz, chunki bu funksiya faqat so'rov
    kelganda (ya'ni webapp.py TO'LIQ yuklangandan keyin) chaqiriladi."""
    from webapp import _authenticate
    return await _authenticate(request)


async def api_products(request: web.Request):
    auth = await _require_auth(request)
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
    auth = await _require_auth(request)
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
    auth = await _require_auth(request)
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

    YANGI - "unit_cost" (ixtiyoriy, musbat son, 1 dona narxi): front-end
    buni FAQAT "Kerak" (olinishi kerak bo'lgan tovarlar) ro'yxatidan
    ochilganda yuboradi, chunki o'sha holatda bu HAQIQIY xarid - shuning
    uchun shu narxdan (unit_cost * qty) moliyaga (Tranzaksiyalar) avtomatik
    "Chiqim" yoziladi (bot tarafidagi handlers/transactions.py bilan bir
    xil db.add_transaction() orqali). Oddiy "Sklad" bo'limidan (yoki
    barkod skanerlab) miqdor qo'shilganda "unit_cost" yuborilmaydi -
    o'shanda moliyaga umuman tegilmaydi (masalan miqdorni to'g'irlash
    uchun, allaqachon hisobga olingan tovar).

    RUXSAT (8-BOSQICH): do'kon egasi har doim qo'sha oladi. Sotuvchi esa
    faqat ega buni yoqib qo'ygan bo'lsa (owners.sellers_can_add_stock,
    standart - yoqilgan) - qarang: access_control.can_add_stock() va
    handlers/sellers.py ("🔐 Sklad ruxsati" tugmasi)."""
    auth = await _require_auth(request)
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

    unit_cost = None
    if body.get("unit_cost") not in (None, ""):
        try:
            unit_cost = float(body.get("unit_cost"))
        except (TypeError, ValueError):
            return web.json_response({"error": "invalid_unit_cost"}, status=400)
        if unit_cost <= 0:
            return web.json_response({"error": "invalid_unit_cost"}, status=400)

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

    # YANGI: "Kerak" ro'yxatidan haqiqiy xarid qilingan bo'lsa - moliyaga
    # "Chiqim" yoziladi (axir tovar sotib olinyapti, pul chiqyapti).
    if unit_cost is not None:
        total_cost = unit_cost * qty
        await db.add_transaction(
            shop_id, "expense", total_cost,
            f"Sklad uchun xarid: {result['name']} — {qty:.0f} dona ({unit_cost:.0f} so'mdan)",
            performed_by=auth["telegram_id"], branch_id=auth.get("branch_id"),
        )

    # 18-BOSQICH: bot tarafidagi savdo oqimi kanaldagi postni avtomatik
    # yangilaganidek (handlers/sales.py), Mini App orqali miqdor
    # o'zgarganda ham kanal posti yangilanishi kerak - avval bu yerda
    # BUTUNLAY yetishmas edi (qarang: webapp_handlers/sklad_extra.py).
    from webapp_handlers.sklad_extra import sync_channel_post_quantity

    await sync_channel_post_quantity(request.app["bot"], product, result["new_quantity"])

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
    auth = await _require_auth(request)
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

    # 18-BOSQICH: Mini App orqali yaratilgan mahsulot ham (rasmsiz,
    # matnli shaklda) kanalga post qilinadi - bot tarafidagi rasm bilan
    # postlashga o'xshab, qarang: webapp_handlers/sklad_extra.py.
    from webapp_handlers.sklad_extra import post_new_product_to_channel

    channel_message_id = await post_new_product_to_channel(
        request.app["bot"], name, price, sell_price, quantity
    )

    product_id = await db.add_product(
        shop_id, name, price, quantity, None, channel_message_id=channel_message_id,
        sell_price=sell_price, min_price=min_price, alert_quantity=alert_quantity, barcode=barcode,
    )

    try:
        await db.log_action(
            shop_id, auth["telegram_id"], "Veb-ilova orqali yangi mahsulot qo'shildi",
            f"{name} — {quantity:.0f} dona" + (f", barkod: {barcode}" if barcode else ""),
        )
    except Exception:
        logger.warning("WebApp yangi mahsulot log_action xatosi", exc_info=True)

    # YANGI: "Kerak" ro'yxatidagi qo'lda qo'shilgan tovarni "✅ olindi" deb
    # belgilab, shu oyna orqali (haqiqiy narx bilan) skladga qo'shilganda -
    # bu HAQIQIY xarid, shuning uchun moliyaga (Tranzaksiyalar) tannarx *
    # miqdor bo'yicha avtomatik "Chiqim" yoziladi. Oddiy "+ Yangi mahsulot"
    # orqali (front-end "is_purchase" yubormaydi) moliyaga tegilmaydi.
    if body.get("is_purchase") and price > 0 and quantity > 0:
        total_cost = price * quantity
        await db.add_transaction(
            shop_id, "expense", total_cost,
            f"Sklad uchun xarid: {name} — {quantity:.0f} dona ({price:.0f} so'mdan)",
            performed_by=auth["telegram_id"], branch_id=auth.get("branch_id"),
        )

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
    auth = await _require_auth(request)
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
    auth = await _require_auth(request)
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


# ---------- OLINISHI KERAK BO'LGAN TOVARLAR - MINI APP ----------
# handlers/products.py'dagi "🧾 Olinishi kerak bo'lgan tovarlar" bo'limi
# bilan AYNAN BIR XIL ma'lumot manbai (db.get_low_stock_products +
# db.get_manual_restock_items) - faqat mini app'dan chaqirilishi uchun.
# Do'kon egasi HAM, sotuvchi HAM ko'ra oladi; faqat do'kon egasi
# "sotib olindi" deb belgilay oladi - qarang: keyboards.restock_kb(manage=...)
# bilan bir xil qoida (front-end "manage" maydoniga qarab tugmalarni
# ko'rsatadi/yashiradi).

async def api_restock_list(request: web.Request):
    auth = await _require_auth(request)
    if not auth:
        return web.json_response({"error": "unauthorized"}, status=401)
    if auth["role"] not in ("owner", "seller"):
        return web.json_response({"error": "not_applicable"}, status=404)

    shop_id = auth["shop_id"]
    low_stock = await db.get_low_stock_products(shop_id)
    manual_items = await db.get_manual_restock_items(shop_id)

    return web.json_response({
        "manage": auth["role"] == "owner",
        "low_stock": [_product_payload(p) for p in low_stock],
        "manual_items": [
            {"id": item["id"], "name": item["name"], "note": item.get("note")}
            for item in manual_items
        ],
    })


async def api_restock_add(request: web.Request):
    """Bot tarafidagi "➕ Qo'lda qo'shish" (restock_add_start/_name/_note,
    handlers/products.py) bilan bir xil - do'kon egasi HAM, sotuvchi HAM
    qo'sha oladi (bu tugma keyboards.restock_kb'da manage'dan qat'i
    nazar har doim ko'rinadi)."""
    auth = await _require_auth(request)
    if not auth:
        return web.json_response({"error": "unauthorized"}, status=401)
    if auth["role"] not in ("owner", "seller"):
        return web.json_response({"error": "not_applicable"}, status=404)

    try:
        body = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "invalid_json"}, status=400)

    name = (body.get("name") or "").strip()
    if not name:
        return web.json_response({"error": "missing_name"}, status=400)
    note = (body.get("note") or "").strip() or None

    shop_id = auth["shop_id"]
    # Bot tarafidagi restock_add_name bilan bir xil tekshiruv - agar shu
    # nomdagi mahsulot skladda allaqachon bo'lsa, ro'yxatga qo'shish o'rniga
    # foydalanuvchini ogohlantiramiz (u "Sklad"dan miqdor qo'shishi kerak).
    existing = await db.find_product_by_name(shop_id, name)
    if existing:
        return web.json_response({
            "error": "product_exists",
            "product": _product_payload(existing),
        }, status=400)

    await db.add_manual_restock_item(shop_id, name, note)
    return web.json_response({"ok": True})


async def api_restock_delete_manual(request: web.Request):
    """Qo'lda qo'shilgan tovarni ro'yxatdan olib tashlaydi - front-end shuni
    mahsulot ALLAQACHON (yangi mahsulot sifatida) skladga qo'shilgandan
    keyin chaqiradi (qarang: app.js saveSkladNewProduct), xuddi bot
    tarafidagi _finalize_restock_purchase()dagi db.delete_manual_restock_item()
    chaqiruviga o'xshab. FAQAT do'kon egasi - bot tarafida ham bu amalni
    faqat manage=True (owner) bajara oladi."""
    auth = await _require_auth(request)
    if not auth:
        return web.json_response({"error": "unauthorized"}, status=401)
    if auth["role"] != "owner":
        return web.json_response({"error": "forbidden"}, status=403)

    try:
        body = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "invalid_json"}, status=400)

    try:
        item_id = int(body.get("id"))
    except (TypeError, ValueError):
        return web.json_response({"error": "invalid_item"}, status=400)

    shop_id = auth["shop_id"]
    item = await db.get_manual_restock_item(shop_id, item_id)
    if not item:
        return web.json_response({"error": "not_found"}, status=400)

    await db.delete_manual_restock_item(shop_id, item_id)
    return web.json_response({"ok": True})



def register_routes(app: web.Application) -> None:
    """webapp.py'ning create_web_app() ichidan chaqiriladi."""
    app.router.add_get("/api/webapp/products", api_products)
    app.router.add_get("/api/webapp/products/by-barcode", api_product_by_barcode)
    app.router.add_get("/api/webapp/sklad/products", api_sklad_products)
    app.router.add_post("/api/webapp/sklad/add-quantity", api_sklad_add_quantity)
    app.router.add_post("/api/webapp/sklad/create-product", api_sklad_create_product)
    app.router.add_post("/api/webapp/sklad/update-product", api_sklad_update_product)
    app.router.add_get("/api/webapp/sklad/history", api_sklad_history)
    app.router.add_get("/api/webapp/restock", api_restock_list)
    app.router.add_post("/api/webapp/restock/add", api_restock_add)
    app.router.add_post("/api/webapp/restock/delete-manual", api_restock_delete_manual)
