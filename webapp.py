"""WEB APP (SAVDO/SKLAD/ADMIN) - ASOSIY FAYL (20-BOSQICH: REFAKTORING).

Bu modul avval BARCHA Mini App REST API endpointlarini (savdo, sklad,
filiallar, sotuvchilar, qarzlar, hisobotlar, obuna, admin paneli va h.k.)
o'z ichiga olgan yagona ~1600 qatorli fayl edi. 20-bosqichda bu fayl
"barcha routerlarni yig'uvchi asosiy fayl"ga aylantirildi:

- Har bir mavzu (sklad, savdo, admin, statik fayllar) endi o'zining
  alohida webapp_handlers/*.py moduliga ko'chirilgan - har biri o'z
  register_routes(app) funksiyasiga ega.
- BU FAYLDA endi faqat ENG ASOSIY, HAMMA MODUL TAYANADIGAN narsalar
  qoladi: initData HMAC tekshiruvi (_verify_init_data), autentifikatsiya
  (_authenticate - boshqa modullar buni "from webapp import
  _authenticate" orqali lokal/lazy import qiladi, aylanma importdan
  qochish uchun), profil/identifikatsiya endpointlari (api_me,
  api_profile), va create_web_app() - u BARCHA modullarning
  register_routes()'ini chaqiradi.

XATTI-HARAKAT HECH QAYERDA O'ZGARMADI - bu FAQAT fayllarni qayta
tashkil qilish (kod ko'chirish), yangi funksionallik yo'q.
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

    # YANGI: "Xush kelibsiz, ..." kabi joylarda Telegramning o'zidagi
    # ismi (first_name) o'rniga, ro'yxatdan o'tishda O'ZI kiritgan ismi
    # ko'rsatiladi (do'kon egasida - owners.full_name, sotuvchida -
    # sellers.seller_name, u bo'lmasa sellers.full_name) - shu ism aniq
    # bo'lmasa, Telegramdagi first_name'ga tushib qoladi (zaxira).
    entered_name = None
    if role == "owner":
        owner = await db.get_owner(telegram_id)
        entered_name = owner and owner.get("full_name")
    elif role == "seller":
        seller = await db.get_seller(telegram_id)
        entered_name = seller and (seller.get("seller_name") or seller.get("full_name"))

    return {
        "telegram_id": telegram_id,
        "shop_id": shop_id,
        "role": role,
        "branch_id": branch_id,
        "name": entered_name or parsed["user"].get("first_name", ""),
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


def create_web_app(bot) -> web.Application:
    """Bitta aiohttp Application yaratadi - unga main.py kerak bo'lsa
    (WEBHOOK_HOST sozlangan bo'lsa) Telegram webhook route'ini ham
    qo'shib qo'yadi. Bu ilova PORT'da doim (polling bo'lsa ham) ishga
    tushiriladi - aks holda WebApp'ning HTTPS manzili ishlamay qoladi.

    20-BOSQICH: REFAKTORING - endi bu funksiya faqat webapp_handlers/*
    modullarining register_routes()'ini chaqiradi (+ shu faylda qolgan
    ikkita "core" endpoint: api_me, api_profile). Har bir modul o'zi
    ichida _authenticate'ni webapp.py'dan LOKAL import qiladi (aylanma
    importdan qochish uchun) - shuning uchun bu importlar pastda,
    funksiya ICHIDA turibdi, yuqorida emas."""
    app = web.Application()
    app["bot"] = bot

    app.router.add_get("/api/webapp/me", api_me)
    app.router.add_get("/api/webapp/profile", api_profile)

    # YANGI: BOSH SAHIFA (dashboard) - mini app'ning yangi kirish ekrani.
    from webapp_handlers.dashboard import register_routes as _register_dashboard_routes
    _register_dashboard_routes(app)

    # 1-BLOK, 1-BOSQICH: SOTUVCHILAR + SKLAD RUXSATI (20-bosqichda
    # api_sklad_permission_set ham shu modulga ko'chirildi).
    from webapp_handlers.sellers import register_routes as _register_sellers_routes
    _register_sellers_routes(app)

    # 2-BLOK, 3-BOSQICH: FILIALLAR TO'LIQ BOSHQARUVI (20-bosqichda
    # ro'yxat/almashtirish - api_branches_list/api_branches_switch - ham
    # shu modulga ko'chirildi).
    from webapp_handlers.branches import register_routes as _register_branches_routes
    _register_branches_routes(app)

    # 3-BLOK, 5-BOSQICH: QARZLAR (mini app).
    from webapp_handlers.debts import register_routes as _register_debts_routes
    _register_debts_routes(app)

    # 4-BLOK, 7-BOSQICH: KIRIM/CHIQIM TRANZAKSIYALAR (mini app).
    from webapp_handlers.transactions import register_routes as _register_transactions_routes
    _register_transactions_routes(app)

    # 5-BLOK, 9-BOSQICH: HISOBOTLAR (mini app).
    from webapp_handlers.reports import register_routes as _register_reports_routes
    _register_reports_routes(app)

    # 6-BLOK, 11-BOSQICH: SOZLAMALAR (mini app).
    from webapp_handlers.settings import register_routes as _register_settings_routes
    _register_settings_routes(app)

    # 7-BLOK, 13-BOSQICH: OBUNA / TO'LOV (mini app).
    from webapp_handlers.subscription import register_routes as _register_subscription_routes
    _register_subscription_routes(app)

    # 8-BLOK, 15-BOSQICH: RO'YXATDAN O'TISH / TAKLIF HAVOLASI (mini app).
    from webapp_handlers.onboarding import register_routes as _register_onboarding_routes
    _register_onboarding_routes(app)

    # 9-BLOK, 18-BOSQICH: SKLAD QO'SHIMCHALARI (AI buyurtma tavsiyasi,
    # veb-ilova orqali yaratilgan mahsulotlar uchun kanal posti).
    from webapp_handlers.sklad_extra import register_routes as _register_sklad_extra_routes
    _register_sklad_extra_routes(app)

    # 10-BLOK, 20-BOSQICH: SKLAD YADROSI (mahsulotlar ro'yxati, barkod,
    # sklad CRUD, tarix, "olinishi kerak bo'lgan tovarlar") - ilgari
    # to'g'ridan-to'g'ri shu faylda edi.
    from webapp_handlers.sklad_core import register_routes as _register_sklad_core_routes
    _register_sklad_core_routes(app)

    # 11-BLOK, 20-BOSQICH: SAVDO YAKUNI (cross-sell + sotishni yakunlash) -
    # ilgari to'g'ridan-to'g'ri shu faylda edi.
    from webapp_handlers.sale import register_routes as _register_sale_routes
    _register_sale_routes(app)

    # 12-BLOK, 20-BOSQICH: BOSH ADMIN PANELI - ilgari to'g'ridan-to'g'ri
    # shu faylda edi (~480 qator).
    from webapp_handlers.admin import register_routes as _register_admin_routes
    _register_admin_routes(app)

    # 13-BLOK, 20-BOSQICH: STATIK FAYLLAR (index.html/app.js/style.css) -
    # ilgari to'g'ridan-to'g'ri shu faylda edi.
    from webapp_handlers.static_files import register_routes as _register_static_routes
    _register_static_routes(app)

    async def health(request):
        return web.json_response({"status": "ok"})

    app.router.add_get("/health", health)

    return app
