"""KIRIM/CHIQIM TRANZAKSIYALAR - MINI APP (4-BLOK, 7-BOSQICH: BACKEND).

Bu modul do'kon egasi/sotuvchi Mini App'dagi "Tranzaksiyalar" bo'limi
orqali:
- qo'lda kirim/chiqim yozuvi qo'shish,
- so'nggi tranzaksiyalar ro'yxatini (+ umumiy kirim/chiqim/balans) ko'rish

qila olishi uchun REST API endpointlarini o'z ichiga oladi.

MUHIM - BIR XILLIK: har bir amal handlers/transactions.py (bot tarafi)dagi
bilan AYNAN BIR XIL database.py funksiyalaridan (db.add_transaction /
db.get_transactions / db.get_totals) foydalanadi - shu sababli ikkala
tarafda ham natija bir xil bo'ladi. "Chiqim" uchun shubhali holat
tekshiruvi (alerts.evaluate_expense_suspicions / send_suspicious_alert)
ham bot tarafidagi _add_transaction_locked() bilan AYNAN BIR XIL
chaqiriladi - shu sababli mini app orqali qo'shilgan katta chiqim ham
do'kon egasiga Telegram orqali ogohlantirish yuboradi (xuddi bot
orqali qo'shilgandek).

KIM FOYDALANA OLADI:
- "Kirim" qo'shish - FAQAT haqiqiy do'kon egasi (bot tarafidagi
  add_income_start() dagi qo'shimcha db.is_owner() tekshiruvi bilan
  bir xil - _require_shop() bitta o'zi yetarli emas, chunki sotuvchida
  ham shop_id bor).
- "Chiqim" qo'shish va ro'yxatni ko'rish - do'kon egasi HAM, sotuvchi
  HAM (bot tarafidagi add_expense_start() / today_status() bilan bir
  xil - faqat _require_shop(), is_owner() tekshiruvisiz).

DIQQAT - RO'YXAT HAQIDA: bot tarafida barcha tranzaksiyalarni sanab
o'tuvchi alohida ekran YO'Q (faqat "📈 Bugungi holat" - jami kirim/
chiqim/balans, va "🔎 Savdolarni qidirish" - faqat savdolar bo'yicha).
db.get_transactions() esa savdo/qarz/qo'lda kiritilgan barcha
yozuvlarni (bitta "transactions" jadvalidan) birga qaytaradi - shu
sababli mini app'dagi ro'yxat HAM shunday, TO'LIQ moliyaviy jurnal
sifatida ko'rsatiladi (buni ajratib olish uchun bazaga yangi ustun
kerak bo'lardi - reja qoidasiga ko'ra database.py'ga tegilmaydi).
"""

import logging
from datetime import datetime

from aiohttp import web

import database as db
import alerts

logger = logging.getLogger(__name__)


async def _require_shop_auth(request: web.Request):
    """webapp._authenticate orqali autentifikatsiya qiladi va do'kon
    egasi YOKI sotuvchiga (lekin bosh adminga EMAS) ruxsat beradi - xuddi
    webapp_handlers/debts.py dagi bir xil nomli funksiya kabi (aylanma
    import haqidagi izoh ham o'sha yerdagi bilan bir xil sabab)."""
    from webapp import _authenticate

    auth = await _authenticate(request)
    if not auth:
        return None, web.json_response({"error": "unauthorized"}, status=401)
    if auth["role"] not in ("owner", "seller"):
        return None, web.json_response({"error": "not_applicable"}, status=404)
    return auth, None


def _tx_payload(t: dict, my_telegram_id: int) -> dict:
    """Ro'yxat javobi uchun bitta xil shakl - sana tayyor (kun.oy.yil
    soat:min) formatda, performed_by esa so'rov yuborgan foydalanuvchi
    bilan solishtirib "Siz" deb belgilanadi (front-end shuni ko'rsatadi,
    aks holda xom telegram_id chiqib ketmasligi uchun)."""
    created = t.get("created_at")
    try:
        created_fmt = datetime.strptime(created, "%Y-%m-%d %H:%M:%S").strftime("%d.%m.%Y %H:%M")
    except (TypeError, ValueError):
        created_fmt = created

    performed_by = t.get("performed_by")
    return {
        "id": t["id"],
        "type": t["type"],
        "amount": t["amount"],
        "description": t.get("description"),
        "created_at": created_fmt,
        "payment_method": t.get("payment_method"),
        "is_mine": bool(performed_by) and performed_by == my_telegram_id,
    }


async def api_transactions_list(request: web.Request):
    """GET /api/webapp/transactions?limit=100 - joriy do'konning so'nggi
    tranzaksiyalari (savdo/qarz/qo'lda kiritilgan - hammasi birga, eng
    yangisidan boshlab) + umumiy kirim/chiqim/balans (db.get_totals bilan
    bir xil - "📈 Bugungi holat" bot ekranidagi kabi, lekin nomi umumiy
    "totals", chunki chegara sanasiz - db.get_totals ham shunday)."""
    auth, err = await _require_shop_auth(request)
    if err:
        return err
    shop_id = auth["shop_id"]

    try:
        limit = int(request.query.get("limit", 100))
        limit = max(1, min(limit, 500))
    except (TypeError, ValueError):
        limit = 100

    transactions = await db.get_transactions(shop_id, limit=limit)
    income, expense = await db.get_totals(shop_id)

    return web.json_response({
        "transactions": [_tx_payload(t, auth["telegram_id"]) for t in transactions],
        "income": income,
        "expense": expense,
        "balance": income - expense,
    })


async def api_transactions_create(request: web.Request):
    """POST /api/webapp/transactions - body: {"type": "income"|"expense",
    "amount", "description"}. "income" FAQAT do'kon egasiga ruxsat
    etiladi (bot tarafidagi qo'shimcha is_owner() tekshiruvi bilan bir
    xil). Muvaffaqiyatli qo'shilgach, "expense" uchun bot tarafidagi
    bilan AYNAN BIR XIL shubhali holat tekshiruvi ishga tushadi."""
    auth, err = await _require_shop_auth(request)
    if err:
        return err
    shop_id = auth["shop_id"]

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid_json"}, status=400)

    type_ = body.get("type")
    if type_ not in ("income", "expense"):
        return web.json_response({"error": "invalid_type"}, status=400)

    if type_ == "income" and auth["role"] != "owner":
        return web.json_response({"error": "owner_only"}, status=403)

    try:
        amount = float(str(body.get("amount")).replace(",", ".").replace(" ", ""))
        if amount <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return web.json_response({"error": "invalid_amount"}, status=400)

    description = (body.get("description") or "").strip()
    if not description:
        return web.json_response({"error": "empty_description"}, status=400)

    tx_id = await db.add_transaction(
        shop_id, type_, amount, description,
        performed_by=auth["telegram_id"], branch_id=auth["branch_id"],
    )

    if type_ == "expense":
        suspicious_flags = await alerts.evaluate_expense_suspicions(
            shop_id, amount, performed_by=auth["telegram_id"]
        )
        if suspicious_flags:
            logger.warning(f"[SHUBHALI - CHIQIM] shop={shop_id}: " + " | ".join(suspicious_flags))
            bot = request.app["bot"]
            await alerts.send_suspicious_alert(bot, shop_id, suspicious_flags, "chiqim")

    income, expense = await db.get_totals(shop_id)
    return web.json_response({
        "id": tx_id,
        "income": income,
        "expense": expense,
        "balance": income - expense,
    })


def register_routes(app: web.Application) -> None:
    """webapp.py'ning create_web_app() ichidan chaqiriladi - shu
    modulning barcha route'larini bitta joyda ro'yxatdan o'tkazadi."""
    app.router.add_get("/api/webapp/transactions", api_transactions_list)
    app.router.add_post("/api/webapp/transactions", api_transactions_create)
