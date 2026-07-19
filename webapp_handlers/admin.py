"""BOSH ADMIN PANELI - MINI APP (20-BOSQICH: REFAKTORING).

Bu modul ilgari webapp.py ichida to'g'ridan-to'g'ri yozilgan edi
(11-BOSQICHda qo'shilgan). 20-bosqichda webapp.py'ni "barcha
routerlarni yig'uvchi asosiy fayl"ga aylantirish maqsadida BU YERGA
ko'chirildi - XATTI-HARAKAT BUTUNLAY O'ZGARMADI, faqat joyi o'zgardi.

Ilgari bosh admin ("do'kon egalarini boshqarish, obuna, to'lovlar,
adminlar, ommaviy xabar) FAQAT botning matnli menyusi orqali ishlagan
(handlers/users.py, handlers/subscription.py). Endi shu FUNKSIYALARNING
HAMMASI mini appda ham ("🛠 Admin" ekrani) ishlaydi - matnli menyu HECH
QAERDA o'chirilmadi, ikkalasi PARALLEL ishlaydi.

Pastdagi funksiyalar business-mantiqni QAYTA YOZMAYDI - ular
database.py/access_control.py'dagi bot handlerlari ishlatgan XUDDI O'SHA
funksiyalarni chaqiradi, faqat natijani Telegram xabari o'rniga JSON
qilib qaytaradi. Shu sababli bot orqali va mini app orqali qilingan
amallar bir-biriga to'liq mos.
"""

import json
import logging

from aiohttp import web

import database as db
import access_control
from handlers.users import SETTING_LABELS, PRICE_SETTING_KEYS

logger = logging.getLogger(__name__)


async def _require_admin(request: web.Request):
    """Barcha /api/webapp/admin/* endpointlar uchun umumiy tekshiruv.

    Muvaffaqiyatli bo'lsa (auth_dict, None) qaytaradi. Muvaffaqiyatsiz
    bo'lsa (None, tayyor_javob) qaytaradi - chaqiruvchi shunchaki
    ``if err: return err`` qilishi kifoya, har bir endpointda 401/403'ni
    alohida yozish shart emas.

    Aylanma import (webapp.py <-> webapp_handlers/admin.py)dan qochish
    uchun import shu yerda (funksiya ichida) - xavfsiz, chunki bu funksiya
    faqat so'rov kelganda (ya'ni webapp.py TO'LIQ yuklangandan keyin)
    chaqiriladi."""
    from webapp import _authenticate
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



def register_routes(app: web.Application) -> None:
    """webapp.py'ning create_web_app() ichidan chaqiriladi."""
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
