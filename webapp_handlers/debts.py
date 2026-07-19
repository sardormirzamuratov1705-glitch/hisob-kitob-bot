"""QARZLAR - MINI APP (3-BLOK, 5-BOSQICH: BACKEND).

Bu modul do'kon egasi/sotuvchi Mini App'dagi "Qarzlar" bo'limi orqali:
- qarzdorlar ro'yxatini ko'rish (+ umumiy qarzdorlik summasi),
- yangi qarz qo'shish,
- qarzga to'liq/qisman to'lov qabul qilish (naqd/plastik/aralash),
- mijozga eslatma yuborish va shaxsiy linkni olish

qila olishi uchun REST API endpointlarini o'z ichiga oladi.

MUHIM - BIR XILLIK: har bir amal handlers/debts.py (bot tarafi)dagi bilan
AYNAN BIR XIL database.py funksiyalaridan (db.add_debt / db.get_debts /
db.add_debt_payment / db.get_overdue_debts va h.k.) foydalanadi - shu
sababli ikkala tarafda ham natija bir xil bo'ladi. Sana parslash
(_parse_taken_date/_parse_due_date) va shaxsiy link yasash (_debt_link)
mantig'i ham handlers/debts.py dagi bilan AYNAN BIR XIL, lekin reja
qoidasiga ko'ra ("hech bir bosqich handlers/*.py'ga tegmaydi") o'sha
fayldan import QILINMADI - buning o'rniga shu modul ICHIDA mustaqil
nusxa sifatida takrorlandi (xuddi webapp_handlers/branches.py'dagi
_rename_branch_row bilan bir xil yondashuv).

KIM FOYDALANA OLADI: bot tarafida bu bo'lim ham do'kon egasiga, ham
sotuvchiga ochiq (access_control.get_shop_id ikkalasiga ham shop_id
qaytaradi - qarang: handlers/debts.py dagi _require_shop). Shu sababli
bu yerda ham role == "owner" YOKI "seller" bo'lsa ruxsat beriladi
(faqat bosh admin rad etiladi) - webapp_handlers/sellers.py va
webapp_handlers/branches.py dagi "faqat owner" cheklovidan FARQLI.
"""

import logging
from datetime import datetime, timedelta

from aiohttp import web

import config
import database as db
import alerts

logger = logging.getLogger(__name__)


async def _require_shop_auth(request: web.Request):
    """webapp._authenticate orqali autentifikatsiya qiladi va do'kon
    egasi YOKI sotuvchiga (lekin bosh adminga EMAS) ruxsat beradi - xuddi
    bot tarafidagi handlers/debts.py._require_shop() bilan bir xil
    qoida (get_shop_id allaqachon adminga None qaytaradi, shu sababli
    admin _authenticate bosqichidayoq 401 bilan chetlanadi - shunga
    qaramay role ni ANIQ tekshiramiz, chunki xavfsizlik uchun ikki marta
    tekshirish ortiqcha emas).

    Aylanma import (webapp.py <-> webapp_handlers/debts.py)dan qochish
    uchun _authenticate shu yerda, funksiya ICHIDA import qilinadi."""
    from webapp import _authenticate

    auth = await _authenticate(request)
    if not auth:
        return None, web.json_response({"error": "unauthorized"}, status=401)
    if auth["role"] not in ("owner", "seller"):
        return None, web.json_response({"error": "not_applicable"}, status=404)
    return auth, None


async def _debt_link(bot, debt_id: int) -> str:
    """handlers/debts.py dagi _debt_link() bilan AYNAN BIR XIL - mijoz
    shu linkni bosib botni ochsa, unga to'g'ridan-to'g'ri eslatma yuborish
    mumkin bo'ladi (qarang: database.link_debt_customer, main.py dagi
    /start deep-link ishlovchisi)."""
    me = await bot.get_me()
    return f"https://t.me/{me.username}?start=debt_{debt_id}"


def _parse_taken_date(text: str) -> str:
    """handlers/debts.py dagi bilan bir xil: 'kun.oy.yil' -> 'YYYY-MM-DD'."""
    dt = datetime.strptime(text.strip(), "%d.%m.%Y")
    return dt.strftime("%Y-%m-%d")


def _parse_due_date(text: str):
    """handlers/debts.py dagi bilan bir xil: '-' -> None, butun son ->
    bugundan shuncha kun keyin, 'kun.oy.yil' -> aniq sana."""
    text = text.strip()
    if not text or text == "-":
        return None
    if text.isdigit():
        due = config.now() + timedelta(days=int(text))
        return due.strftime("%Y-%m-%d")
    due = datetime.strptime(text, "%d.%m.%Y")
    return due.strftime("%Y-%m-%d")


def _debt_payload(d: dict) -> dict:
    """Ro'yxat/qo'shish javoblari uchun bitta xil shakl - list_debts()
    (bot tarafi) ko'rsatadigan ma'lumotlar bilan bir xil tarkib, lekin
    JSON uchun tuzilgan va sanalar tayyor (kun.oy.yil) formatda."""
    paid_amount = d.get("paid_amount") or 0
    remaining = d["amount"] - paid_amount

    def _fmt(date_str):
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d.%m.%Y")
        except ValueError:
            return None

    days_ago = None
    try:
        created_dt = datetime.strptime(d["created_at"], "%Y-%m-%d %H:%M:%S")
        days_ago = (config.now() - created_dt).days
    except (TypeError, ValueError, KeyError):
        pass

    days_left = None
    if d.get("due_date"):
        try:
            due_dt = datetime.strptime(d["due_date"], "%Y-%m-%d")
            days_left = (due_dt.date() - config.now().date()).days
        except ValueError:
            pass

    return {
        "id": d["id"],
        "customer_name": d["customer_name"],
        "phone": d.get("phone"),
        "amount": d["amount"],
        "paid_amount": paid_amount,
        "remaining": remaining,
        "is_paid": bool(d.get("is_paid")),
        "description": d.get("description"),
        "taken_date": _fmt(d.get("taken_date")),
        "due_date": _fmt(d.get("due_date")),
        "days_ago": days_ago,
        "days_left": days_left,
        "customer_linked": bool(d.get("customer_chat_id")),
    }


async def api_debts_list(request: web.Request):
    """GET /api/webapp/debts?all=1 - joriy do'konning qarzdorlari
    ro'yxati + umumiy qarzdorlik summasi. `all=1` bo'lmasa (standart)
    handlers/debts.py list_debts() kabi FAQAT to'lanmagan qarzlar
    qaytariladi."""
    auth, err = await _require_shop_auth(request)
    if err:
        return err
    shop_id = auth["shop_id"]

    only_unpaid = request.query.get("all") != "1"
    debts = await db.get_debts(shop_id, only_unpaid=only_unpaid)
    total = await db.get_total_debt(shop_id)

    return web.json_response({
        "debts": [_debt_payload(d) for d in debts],
        "total_debt": total,
    })


async def api_debts_create(request: web.Request):
    """POST /api/webapp/debts - body: {"customer_name", "phone", "amount",
    "description", "taken_date"?, "due_date"?}. taken_date/due_date -
    handlers/debts.py bilan bir xil matn formatlarida ("kun.oy.yil",
    bo'sh/"-"/son) qabul qilinadi; berilmasa - taken_date bugungi kun,
    due_date esa sanasiz qoldiriladi (bot tarafidagi standart bilan bir
    xil). Muvaffaqiyatli qo'shilgach, javobda shaxsiy link ham
    qaytariladi (front-end shuni ko'rsatib, mijozga yuborish imkonini
    berishi mumkin - xuddi bot tarafidagi kabi)."""
    auth, err = await _require_shop_auth(request)
    if err:
        return err
    shop_id = auth["shop_id"]

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid_json"}, status=400)

    customer_name = (body.get("customer_name") or "").strip()
    if not customer_name:
        return web.json_response({"error": "empty_customer_name"}, status=400)

    phone = (body.get("phone") or "").strip() or "-"

    try:
        amount = float(str(body.get("amount")).replace(",", ".").replace(" ", ""))
        if amount <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return web.json_response({"error": "invalid_amount"}, status=400)

    description = (body.get("description") or "").strip() or "-"

    taken_date = None
    taken_raw = (body.get("taken_date") or "").strip()
    if taken_raw:
        try:
            taken_date = _parse_taken_date(taken_raw)
        except ValueError:
            return web.json_response({"error": "invalid_taken_date"}, status=400)

    due_date = None
    due_raw = (body.get("due_date") or "").strip()
    if due_raw:
        try:
            due_date = _parse_due_date(due_raw)
        except ValueError:
            return web.json_response({"error": "invalid_due_date"}, status=400)

    debt_id = await db.add_debt(
        shop_id, customer_name, phone, amount, description,
        due_date=due_date, taken_date=taken_date,
        performed_by=auth["telegram_id"], branch_id=auth["branch_id"],
    )

    debt = await db.get_debt(shop_id, debt_id)
    bot = request.app["bot"]
    link = await _debt_link(bot, debt_id)

    return web.json_response({"debt": _debt_payload(debt), "link": link})


async def api_debts_pay(request: web.Request):
    """POST /api/webapp/debts/pay - body: {"debt_id", "amount",
    "payment_method": "naqd"|"plastik"|"aralash", "cash_amount"?}.
    "aralash" bo'lsa faqat cash_amount kiritiladi (bot tarafidagi
    PayDebt.mixed_cash_amount bilan bir xil g'oya) - qolgan qism
    avtomatik plastik hisoblanadi (card_amount = amount - cash_amount).
    db.add_debt_payment orqali AYNAN BIR XIL natija (transactions'ga
    kirim yozuvi, debts.paid_amount/is_paid yangilanishi)."""
    auth, err = await _require_shop_auth(request)
    if err:
        return err
    shop_id = auth["shop_id"]

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid_json"}, status=400)

    try:
        debt_id = int(body.get("debt_id"))
    except (TypeError, ValueError):
        return web.json_response({"error": "invalid_debt_id"}, status=400)

    debt = await db.get_debt(shop_id, debt_id)
    if not debt:
        return web.json_response({"error": "not_found"}, status=404)
    if debt["is_paid"]:
        return web.json_response({"error": "already_paid"}, status=409)

    remaining_before = debt["amount"] - (debt.get("paid_amount") or 0)

    try:
        amount = float(str(body.get("amount")).replace(",", ".").replace(" ", ""))
        if amount <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return web.json_response({"error": "invalid_amount"}, status=400)

    if amount > remaining_before + 0.0001:
        return web.json_response({"error": "amount_too_large", "remaining": remaining_before}, status=400)

    payment_method = body.get("payment_method")
    if payment_method not in ("naqd", "plastik", "aralash"):
        return web.json_response({"error": "invalid_payment_method"}, status=400)

    kwargs = {}
    if payment_method == "aralash":
        try:
            cash_amount = float(str(body.get("cash_amount")).replace(",", ".").replace(" ", ""))
            if cash_amount < 0 or cash_amount > amount:
                raise ValueError
        except (TypeError, ValueError):
            return web.json_response({"error": "invalid_cash_amount"}, status=400)
        kwargs["cash_amount"] = cash_amount
        kwargs["card_amount"] = amount - cash_amount

    result = await db.add_debt_payment(
        shop_id, debt_id, amount, performed_by=auth["telegram_id"],
        payment_method=payment_method, **kwargs,
    )
    if result is None:
        return web.json_response({"error": "not_found"}, status=404)

    return web.json_response({
        "status": result["status"],
        "paid_amount": result["paid_amount"],
        "remaining": result["remaining"],
    })


async def api_debts_remind(request: web.Request):
    """POST /api/webapp/debts/remind - body: {"debt_id"}. Mijozga
    to'g'ridan-to'g'ri eslatma yuboradi (agar u shaxsiy link orqali
    botga ulangan bo'lsa) - alerts.send_customer_debt_reminder bilan
    AYNAN BIR XIL (bot tarafidagi remind_debt_cb kabi)."""
    auth, err = await _require_shop_auth(request)
    if err:
        return err
    shop_id = auth["shop_id"]

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid_json"}, status=400)

    try:
        debt_id = int(body.get("debt_id"))
    except (TypeError, ValueError):
        return web.json_response({"error": "invalid_debt_id"}, status=400)

    debt = await db.get_debt(shop_id, debt_id)
    if not debt:
        return web.json_response({"error": "not_found"}, status=404)

    bot = request.app["bot"]
    sent = await alerts.send_customer_debt_reminder(bot, debt)
    return web.json_response({"sent": sent})


async def api_debts_link(request: web.Request):
    """GET /api/webapp/debts/link?debt_id=... - mijoz uchun shaxsiy
    linkni qaytaradi (hech narsa yozmaydi/yubormaydi - faqat linkning
    o'zi, front-end buni nusxalash/ulashish uchun ko'rsatadi)."""
    auth, err = await _require_shop_auth(request)
    if err:
        return err
    shop_id = auth["shop_id"]

    try:
        debt_id = int(request.query.get("debt_id"))
    except (TypeError, ValueError):
        return web.json_response({"error": "invalid_debt_id"}, status=400)

    debt = await db.get_debt(shop_id, debt_id)
    if not debt:
        return web.json_response({"error": "not_found"}, status=404)

    bot = request.app["bot"]
    link = await _debt_link(bot, debt_id)
    return web.json_response({"link": link})


def register_routes(app: web.Application) -> None:
    """webapp.py'ning create_web_app() ichidan chaqiriladi - shu
    modulning barcha route'larini bitta joyda ro'yxatdan o'tkazadi."""
    app.router.add_get("/api/webapp/debts", api_debts_list)
    app.router.add_post("/api/webapp/debts", api_debts_create)
    app.router.add_post("/api/webapp/debts/pay", api_debts_pay)
    app.router.add_post("/api/webapp/debts/remind", api_debts_remind)
    app.router.add_get("/api/webapp/debts/link", api_debts_link)
