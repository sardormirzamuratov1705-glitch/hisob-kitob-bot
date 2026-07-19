"""FILIALLAR TO'LIQ BOSHQARUVI - MINI APP (2-BLOK, 3-BOSQICH: BACKEND; 20-BOSQICH: REFAKTORING).

Bu modul do'kon egasi Mini App'dagi "Filiallar" bo'limi orqali:
- filiallar ro'yxatini va joriy filialni ko'rish, boshqasiga o'tish
  (api_branches_list / api_branches_switch - 20-bosqichda webapp.py'dan
  BU YERGA ko'chirildi, xatti-harakat o'zgarmadi),
- yangi filial yaratish, mavjudini nomini o'zgartirish va o'chirish,
qila olishi uchun REST API endpointlarini o'z ichiga oladi.

MUHIM - BIR XILLIK: yaratish va o'chirish uchun database.py'dagi
db.add_branch() / db.ensure_default_branch() / db.delete_branch()
funksiyalari ISHLATILADI - bular handlers/branches.py (bot tarafi)dagi
branch_manage_new_name / branch_delete_cb bilan AYNAN BIR XIL
funksiyalar, shu sababli ikkala tarafda ham natija bir xil bo'ladi.

NOMINI O'ZGARTIRISH ("rename") HAQIDA: database.py'da bunga mos tayyor
funksiya YO'Q (bot tarafida ham bu amal yo'q - handlers/branches.py'da
faqat yaratish/almashtirish/o'chirish bor). Reja qoidasiga ko'ra
("hech bir bosqich database.py'ga tegmaydi") database.py'ga yangi
funksiya QO'SHILMADI - buning o'rniga shu modul ICHIDA, xuddi
database.py'dagi boshqa filial funksiyalari bilan bir xil uslubda
(aiosqlite + config.DB_PATH), to'g'ridan-to'g'ri SQL orqali amalga
oshirildi (pastga qarang: _rename_branch_row). Bu YANGI kod - mavjud
database.py fayli o'zi o'zgarmadi."""

import logging

import aiosqlite
from aiohttp import web

import config
import database as db

logger = logging.getLogger(__name__)


async def _require_owner_auth(request: web.Request):
    """webapp._authenticate orqali autentifikatsiya qiladi va faqat HAQIQIY
    do'kon egasiga (role == "owner") ruxsat beradi - xuddi
    webapp_handlers/sellers.py'dagi bir xil nomli funksiya kabi (aylanma
    import haqidagi izoh ham o'sha yerdagi bilan bir xil sabab)."""
    from webapp import _authenticate

    auth = await _authenticate(request)
    if not auth:
        return None, web.json_response({"error": "unauthorized"}, status=401)
    if auth["role"] != "owner":
        return None, web.json_response({"error": "not_applicable"}, status=404)
    return auth, None


async def _rename_branch_row(shop_id: int, branch_id: int, new_name: str) -> bool:
    """database.py'dagi delete_branch()/add_branch() bilan BIR XIL uslubda
    (aiosqlite + config.DB_PATH, timeout=10) - lekin bu funksiya
    database.py'ning o'zida EMAS, shu modulning ichida (qarang: modul
    boshidagi izoh)."""
    async with aiosqlite.connect(config.DB_PATH, timeout=10) as conn:
        cursor = await conn.execute(
            "UPDATE branches SET name = ? WHERE id = ? AND shop_id = ?",
            (new_name, branch_id, shop_id),
        )
        await conn.commit()
        return cursor.rowcount > 0


async def api_branches_list(request: web.Request):
    """MINI APP ICHIDAN FILIALGA O'TISH: filiallar ro'yxati + joriy filial.
    Faqat HAQIQIY do'kon egasi uchun - sotuvchi o'z filialini o'zi
    almashtira olmaydi (qarang: access_control.get_branch_id izohi,
    handlers/branches.py bilan bir xil qoida)."""
    auth, err = await _require_owner_auth(request)
    if err:
        return err

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
    auth, err = await _require_owner_auth(request)
    if err:
        return err

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


async def api_branches_create(request: web.Request):
    """POST /api/webapp/branches - body: {"name": "..."}. Bot tarafidagi
    branch_manage_new_name() bilan AYNAN BIR XIL: agar bu do'kon uchun
    BIRINCHI filial bo'lsa, avval ensure_default_branch() orqali
    hozirgacha "Bosh filial" deb yashirin yurgan ma'lumotlar do'kon nomi
    bilan birinchi (haqiqiy) filialga aylantiriladi - shundan keyingina
    yangi kiritilgan nom bilan IKKINCHI filial qo'shiladi. Javobda
    default_branch_created shu holatni frontend'ga bildiradi (front-end
    buni alohida xabar sifatida ko'rsatishi mumkin)."""
    auth, err = await _require_owner_auth(request)
    if err:
        return err
    shop_id = auth["shop_id"]

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid_json"}, status=400)

    name = (body.get("name") or "").strip()
    if not name:
        return web.json_response({"error": "empty_name"}, status=400)

    default_branch = await db.ensure_default_branch(shop_id)
    branch = await db.add_branch(shop_id, name)

    branches = await db.get_branches(shop_id)
    owner = await db.get_owner(shop_id)
    current_branch_id = (owner or {}).get("current_branch_id")

    return web.json_response({
        "branch": {"id": branch["id"], "name": branch["name"]},
        "default_branch_created": (
            {"id": default_branch["id"], "name": default_branch["name"]}
            if default_branch else None
        ),
        "branches": [{"id": b["id"], "name": b["name"]} for b in branches],
        "current_branch_id": current_branch_id,
    })


async def api_branches_rename(request: web.Request):
    """POST /api/webapp/branches/rename - body: {"branch_id": .., "name": ".."}.
    db.find_branch_by_name orqali (mavjud database.py funksiyasi) boshqa
    filial bilan bir xil nomga o'zgartirib qo'yilmasligi tekshiriladi -
    xuddi db.add_branch() ichidagi bir xil tekshiruv kabi."""
    auth, err = await _require_owner_auth(request)
    if err:
        return err
    shop_id = auth["shop_id"]

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid_json"}, status=400)

    try:
        branch_id = int(body.get("branch_id"))
    except (TypeError, ValueError):
        return web.json_response({"error": "invalid_branch_id"}, status=400)

    new_name = (body.get("name") or "").strip()
    if not new_name:
        return web.json_response({"error": "empty_name"}, status=400)

    branch = await db.get_branch(shop_id, branch_id)
    if not branch:
        return web.json_response({"error": "not_found"}, status=404)

    duplicate = await db.find_branch_by_name(shop_id, new_name)
    if duplicate and duplicate["id"] != branch_id:
        return web.json_response({"error": "duplicate_name"}, status=409)

    renamed = await _rename_branch_row(shop_id, branch_id, new_name)
    if not renamed:
        return web.json_response({"error": "not_found"}, status=404)

    updated = await db.get_branch(shop_id, branch_id)
    return web.json_response({"branch": {"id": updated["id"], "name": updated["name"]}})


async def api_branches_delete(request: web.Request):
    """POST /api/webapp/branches/delete - body: {"branch_id": ..}.
    db.delete_branch() (mavjud, bot tarafidagi branch_delete_cb bilan bir
    xil) shu filialga tegishli joriy filial/sotuvchi biriktiruvlarini ham
    avtomatik "Bosh filial"ga qaytaradi - qarang: database.py izohi."""
    auth, err = await _require_owner_auth(request)
    if err:
        return err
    shop_id = auth["shop_id"]

    try:
        body = await request.json()
    except Exception:
        body = {}

    try:
        branch_id = int(body.get("branch_id"))
    except (TypeError, ValueError):
        return web.json_response({"error": "invalid_branch_id"}, status=400)

    deleted = await db.delete_branch(shop_id, branch_id)
    if not deleted:
        return web.json_response({"error": "not_found"}, status=404)
    return web.json_response({"ok": True})


def register_routes(app: web.Application) -> None:
    """webapp.py'ning create_web_app() ichidan chaqiriladi."""
    app.router.add_get("/api/webapp/branches", api_branches_list)
    app.router.add_post("/api/webapp/branches/switch", api_branches_switch)
    app.router.add_post("/api/webapp/branches", api_branches_create)
    app.router.add_post("/api/webapp/branches/rename", api_branches_rename)
    app.router.add_post("/api/webapp/branches/delete", api_branches_delete)
