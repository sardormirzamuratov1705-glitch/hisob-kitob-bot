"""SOTUVCHILAR BOSHQARUVI - MINI APP (1-BLOK, 1-BOSQICH: BACKEND).

Bu modul do'kon egasi Mini App'dagi "Sotuvchilar" bo'limi orqali:
- sotuvchilar ro'yxatini ko'rish,
- yangi sotuvchi qo'shish (telegram_id orqali - mini appda xabarni forward
  qilib bo'lmaydi, shuning uchun bot'dagi kabi forward varianti YO'Q),
- sotuvchini o'chirish,
- sotuvchini boshqa filialga ko'chirish,

qila olishi uchun REST API endpointlarini o'z ichiga oladi.

MUHIM - BIR XILLIK: bu yerdagi har bir amal handlers/sellers.py (bot
tarafi)dagi bilan AYNAN BIR XIL database.py funksiyalaridan va bir xil
tekshiruv qoidalaridan (bosh admin bo'la olmaydi, boshqa do'konning
egasi/sotuvchisi bo'la olmaydi va h.k.) foydalanadi - shu sababli ikkala
tarafda ham natija bir xil bo'ladi.

DIQQAT - SKLAD/NARX HUQUQI HAQIDA: joriy bazada (database.py, jadval:
owners.sellers_can_add_stock) sklad huquqi FAQAT do'kon darajasida
saqlanadi - ya'ni "hamma sotuvchiga birdek" yoqiladi/o'chiriladi, HAR BIR
sotuvchi uchun ALOHIDA emas. Bu funksiya allaqachon mavjud
(webapp.api_sklad_permission_set, route: POST /api/webapp/sklad-permission)
- shu sababli bu yerda takrorlanmaydi, faqat api_sellers_list javobida
hozirgi holati (sellers_can_add_stock) qo'shib beriladi, front-end shuni
"Sotuvchilar" ekranida ko'rsatib, o'sha mavjud endpointga murojaat qiladi.

"Narx huquqi" degan alohida tushuncha esa joriy bazada UMUMAN YO'Q (na
do'kon darajasida, na sotuvchi darajasida). Buni qo'shish uchun
database.py'ga yangi ustun/jadval kerak bo'ladi - reja qoidasiga ko'ra
("hech bir bosqich database.py'ga tegmaydi") bu ALOHIDA (kelasi) bosqich
sifatida qaraladi, shu bosqichda ataylab qo'shilmadi.
"""

import logging

from aiohttp import web

import access_control
import database as db

logger = logging.getLogger(__name__)


async def _require_owner_auth(request: web.Request):
    """webapp._authenticate orqali autentifikatsiya qiladi va faqat HAQIQIY
    do'kon egasiga (role == "owner") ruxsat beradi - na bosh admin, na
    sotuvchi sotuvchilar bo'limini boshqara olmaydi (xuddi bot tarafidagi
    _require_owner() kabi).

    Aylanma import (webapp.py <-> webapp_handlers/sellers.py)dan qochish
    uchun _authenticate shu yerda, funksiya ICHIDA import qilinadi - bu
    xavfsiz, chunki bu funksiya faqat so'rov kelganda (ya'ni webapp.py
    to'liq yuklangandan keyin) chaqiriladi.

    Qaytaradi: (auth_dict, None) - muvaffaqiyatli bo'lsa;
               (None, error_response) - xato bo'lsa (chaqiruvchi shu
               javobni to'g'ridan-to'g'ri qaytarishi kerak)."""
    from webapp import _authenticate

    auth = await _authenticate(request)
    if not auth:
        return None, web.json_response({"error": "unauthorized"}, status=401)
    if auth["role"] != "owner":
        return None, web.json_response({"error": "not_applicable"}, status=404)
    return auth, None


def _seller_payload(s: dict, branch_name: str) -> dict:
    """Ro'yxat/qo'shish javoblari uchun bitta xil shakl - handlers/sellers.py
    dagi list_sellers() ko'rsatadigan ma'lumotlar bilan bir xil tarkib
    (ism, telefon, filial), lekin JSON uchun tuzilgan holda."""
    telegram_label = s.get("full_name") or (
        f"@{s['username']}" if s.get("username") else str(s["telegram_id"])
    )
    return {
        "telegram_id": s["telegram_id"],
        "seller_name": s.get("seller_name"),
        "full_name": s.get("full_name"),
        "username": s.get("username"),
        "display_name": s.get("seller_name") or telegram_label,
        "phone_number": s.get("phone_number"),
        "branch_id": s.get("branch_id"),
        "branch_name": branch_name,
    }


async def api_sellers_list(request: web.Request):
    """GET /api/webapp/sellers - joriy do'kon egasining barcha sotuvchilari
    (filial nomi bilan birga) + tanlash uchun filiallar ro'yxati + joriy
    sklad huquqi holati (front-end shu javobdan "Sotuvchilar" ekranini
    bitta so'rovda to'liq quradi)."""
    auth, err = await _require_owner_auth(request)
    if err:
        return err

    shop_id = auth["shop_id"]
    sellers = await db.get_sellers(shop_id)
    branches = await db.get_branches(shop_id)
    branch_map = {b["id"]: b["name"] for b in branches}

    payload = [
        _seller_payload(s, branch_map.get(s.get("branch_id"), "Bosh filial"))
        for s in sellers
    ]
    can_add_stock = await db.get_sellers_can_add_stock(shop_id)

    return web.json_response({
        "sellers": payload,
        "branches": [{"id": b["id"], "name": b["name"]} for b in branches],
        "sellers_can_add_stock": can_add_stock,
    })


async def api_sellers_add(request: web.Request):
    """POST /api/webapp/sellers - yangi sotuvchini FAQAT telegram_id orqali
    qo'shadi (body: {"telegram_id": ...}). Bot tarafidagi add_seller_finish()
    bilan AYNAN BIR XIL tekshiruvlar: bosh admin, boshqa do'konning egasi
    yoki allaqachon (istalgan do'konning) sotuvchisi bo'la olmaydi. Yangi
    sotuvchi joriy do'kon egasining hozirgi filialiga biriktiriladi."""
    auth, err = await _require_owner_auth(request)
    if err:
        return err
    shop_id = auth["shop_id"]

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid_json"}, status=400)

    try:
        target_id = int(str(body.get("telegram_id")).strip())
    except (TypeError, ValueError, AttributeError):
        return web.json_response({"error": "invalid_telegram_id"}, status=400)

    if access_control.is_admin(target_id):
        return web.json_response({"error": "already_admin"}, status=409)
    if await db.is_owner(target_id):
        return web.json_response({"error": "already_owner"}, status=409)
    if await db.is_seller(target_id):
        return web.json_response({"error": "already_seller"}, status=409)

    branch_id = await access_control.get_branch_id(shop_id)
    await db.add_seller(
        target_id, shop_id, None, None, added_by=auth["telegram_id"], branch_id=branch_id
    )

    bot = request.app["bot"]
    try:
        await bot.send_message(
            target_id,
            "✅ Sizga do'kon boshqaruv botidan sotuvchi sifatida foydalanish huquqi berildi.\n"
            "Boshlash uchun /start buyrug'ini bosing.",
        )
    except Exception:
        pass

    seller = await db.get_seller(target_id)
    branches = await db.get_branches(shop_id)
    branch_map = {b["id"]: b["name"] for b in branches}
    branch_name = branch_map.get(seller.get("branch_id"), "Bosh filial")
    return web.json_response({"seller": _seller_payload(seller, branch_name)})


async def api_sellers_remove(request: web.Request):
    """POST /api/webapp/sellers/remove - body: {"telegram_id": ...}.
    db.remove_seller shop_id bilan birga tekshiradi - do'kon egasi faqat
    O'Z sotuvchisini o'chira oladi (xuddi bot tarafidagi remove_seller_cb
    kabi)."""
    auth, err = await _require_owner_auth(request)
    if err:
        return err
    shop_id = auth["shop_id"]

    try:
        body = await request.json()
    except Exception:
        body = {}

    try:
        target_id = int(str(body.get("telegram_id")).strip())
    except (TypeError, ValueError, AttributeError):
        return web.json_response({"error": "invalid_telegram_id"}, status=400)

    removed = await db.remove_seller(shop_id, target_id)
    if not removed:
        return web.json_response({"error": "not_found"}, status=404)
    return web.json_response({"ok": True})


async def api_sellers_set_branch(request: web.Request):
    """POST /api/webapp/sellers/branch - body: {"telegram_id": ..,
    "branch_id": .. YOKI null}. Bot tarafidagi seller_branch_set_cb bilan
    bir xil: branch_id=null -> "Bosh filial", aks holda shu do'konga
    tegishli filial ekani tekshiriladi."""
    auth, err = await _require_owner_auth(request)
    if err:
        return err
    shop_id = auth["shop_id"]

    try:
        body = await request.json()
    except Exception:
        body = {}

    try:
        target_id = int(str(body.get("telegram_id")).strip())
    except (TypeError, ValueError, AttributeError):
        return web.json_response({"error": "invalid_telegram_id"}, status=400)

    branch_id = body.get("branch_id")
    branch_name = "Bosh filial"
    if branch_id is not None:
        try:
            branch_id = int(branch_id)
        except (TypeError, ValueError):
            return web.json_response({"error": "invalid_branch_id"}, status=400)
        branch = await db.get_branch(shop_id, branch_id)
        if not branch:
            return web.json_response({"error": "branch_not_found"}, status=404)
        branch_name = branch["name"]

    moved = await db.set_seller_branch(shop_id, target_id, branch_id)
    if not moved:
        return web.json_response({"error": "not_found"}, status=404)

    return web.json_response({"ok": True, "branch_id": branch_id, "branch_name": branch_name})


def register_routes(app: web.Application) -> None:
    """webapp.py'ning create_web_app() ichidan chaqiriladi - shu modulning
    barcha route'larini bitta joyda ro'yxatdan o'tkazadi."""
    app.router.add_get("/api/webapp/sellers", api_sellers_list)
    app.router.add_post("/api/webapp/sellers", api_sellers_add)
    app.router.add_post("/api/webapp/sellers/remove", api_sellers_remove)
    app.router.add_post("/api/webapp/sellers/branch", api_sellers_set_branch)
