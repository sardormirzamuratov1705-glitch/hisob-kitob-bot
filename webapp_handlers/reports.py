"""HISOBOTLAR - MINI APP (5-BLOK, 9-BOSQICH: BACKEND).

Bu modul do'kon egasi/sotuvchi Mini App'dagi "Hisobotlar" bo'limi orqali
bot tarafidagi handlers/reports.py'dagi quyidagi ekranlarning HAMMASINI
(Excel eksport va bosh admin uchun DB zaxira/tiklashdan tashqari - ular
fayl bilan ishlaydi, JSON API'ga to'g'ri kelmaydi va bu bosqich doirasida
emas) REST API sifatida taqdim etadi:

- 📊 Umumiy hisobot / 🏢 Filial bo'yicha hisobot -> GET .../summary
- 🆚 Filiallar solishtiruvi                      -> GET .../branches-comparison
- 🆚 Sotuvchilar solishtiruvi                     -> GET .../sellers-comparison
- 📈 Oylik prognoz                                -> GET .../forecast
- 📉 Trend tahlili                                -> GET .../trend
- 🏆 Top mahsulotlar                              -> GET .../top-products
- 🔔 Kunlik hisobot (yoqish/o'chirish)             -> GET/POST .../daily-report
- 🚨 Shubhali holatlar (yoqish/o'chirish)          -> GET/POST .../suspicious-alert
- 🗂 Audit jurnali                                -> GET .../audit-log

MUHIM - BIR XILLIK: har bir amal handlers/reports.py (bot tarafi)dagi bilan
AYNAN BIR XIL database.py funksiyalaridan foydalanadi - shu sababli ikkala
tarafda ham natija bir xil bo'ladi. Oylik nomlarini o'zbekchalashtirish
(_format_month_uz) va trend foizini hisoblash (_compute_trend) mantig'i ham
handlers/reports.py dagi bilan AYNAN BIR XIL, lekin reja qoidasiga ko'ra
("hech bir bosqich handlers/*.py'ga tegmaydi") o'sha fayldan import
QILINMADI - buning o'rniga shu modul ICHIDA mustaqil nusxa sifatida
takrorlandi (xuddi webapp_handlers/debts.py'dagi _debt_link bilan bir xil
yondashuv).

KIM FOYDALANA OLADI: bot tarafida BARCHA hisobot ekranlari (shu jumladan
"🔔 Kunlik hisobot" va "🚨 Shubhali holatlar" sozlamalari, hatto "🗂 Audit
jurnali" ham) handlers/reports.py._require_shop() orqali ochiladi - u esa
faqat access_control.get_shop_id()ga tayanadi, is_owner() TEKSHIRMAYDI.
get_shop_id() esa do'kon egasi HAM, sotuvchi HAM uchun shop_id qaytaradi
(qarang: access_control.get_shop_id). Ya'ni bot tarafida sotuvchi ham
BARCHA hisobotlarni ko'radi VA sozlamalarni yoqib/o'chira oladi - bu
bot tarafidagi MAVJUD xatti-harakat, shu sababli bir xillik qoidasiga
ko'ra bu yerda ham o'zgartirilmasdan AYNAN shunday takrorlanadi.
"""

import logging
from datetime import datetime

from aiohttp import web

import database as db

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


def _parse_branch_id(request: web.Request):
    """?branch_id= query parametrini o'qiydi: yo'q/bo'sh bo'lsa - None
    (barcha filiallar birga, "umumiy" hisobot), "0" bo'lsa - 0 (Bosh
    filial), aks holda - shu filial ID'si (int). handlers/reports.py dagi
    kb.report_branch_kb natijasi (callback_data: "0" yoki filial id yoki
    "all") bilan bir xil uch xil holatni aks ettiradi."""
    raw = request.query.get("branch_id")
    if raw is None or raw == "" or raw == "all":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


# ---------- 📊 UMUMIY / 🏢 FILIAL BO'YICHA HISOBOT ----------

async def api_reports_summary(request: web.Request):
    """GET /api/webapp/reports/summary?branch_id=<ixtiyoriy> - branch_id
    berilmasa handlers/reports.py.general_report() bilan bir xil (BARCHA
    filiallar birga + sklad ma'lumoti), berilsa branch_report_show() bilan
    bir xil (bitta filial, sklad ma'lumotisiz - sklad filial kesimida
    saqlanmaydi)."""
    auth, err = await _require_shop_auth(request)
    if err:
        return err
    shop_id = auth["shop_id"]
    branch_id = _parse_branch_id(request)

    branch_name = None
    if branch_id is not None:
        if branch_id:
            branch = await db.get_branch(shop_id, branch_id)
            if not branch:
                return web.json_response({"error": "branch_not_found"}, status=404)
            branch_name = branch["name"]
        else:
            branch_name = "Bosh filial"

    income, expense = await db.get_totals(shop_id, branch_id=branch_id)
    total_debt = await db.get_total_debt(shop_id, branch_id=branch_id)
    payment_totals = await db.get_payment_method_totals(shop_id, "income", branch_id=branch_id)

    result = {
        "branch_id": branch_id,
        "branch_name": branch_name,
        "income": income,
        "expense": expense,
        "balance": income - expense,
        "payment_totals": payment_totals,
        "total_debt": total_debt,
    }

    # Sklad butun do'kon bo'yicha yagona (filial kesimida saqlanmaydi) -
    # shuning uchun FAQAT "umumiy" (branch_id yo'q) so'rovda qaytariladi,
    # xuddi bot tarafidagi general_report()da bor-u, branch_report_show()da
    # yo'qligi kabi.
    if branch_id is None:
        products = await db.get_all_products(shop_id)
        result["products_count"] = len(products)
        result["total_stock_value"] = sum(p["price"] * p["quantity"] for p in products)

    return web.json_response(result)


# ---------- 🆚 FILIALLAR / SOTUVCHILAR SOLISHTIRUVI ----------

async def api_reports_branches_comparison(request: web.Request):
    """GET /api/webapp/reports/branches-comparison - foyda bo'yicha
    kamayish tartibida (db.get_branch_comparison bilan bir xil)."""
    auth, err = await _require_shop_auth(request)
    if err:
        return err
    rows = await db.get_branch_comparison(auth["shop_id"])
    return web.json_response({"branches": rows})


async def api_reports_sellers_comparison(request: web.Request):
    """GET /api/webapp/reports/sellers-comparison - foyda bo'yicha
    kamayish tartibida (db.get_seller_comparison bilan bir xil)."""
    auth, err = await _require_shop_auth(request)
    if err:
        return err
    rows = await db.get_seller_comparison(auth["shop_id"])
    return web.json_response({"sellers": rows})


# ---------- 📈 OYLIK PROGNOZ / 📉 TREND TAHLILI ----------

_UZ_MONTHS = {
    "01": "Yanvar", "02": "Fevral", "03": "Mart", "04": "Aprel", "05": "May", "06": "Iyun",
    "07": "Iyul", "08": "Avgust", "09": "Sentabr", "10": "Oktabr", "11": "Noyabr", "12": "Dekabr",
}


def _format_month_uz(month_key: str) -> str:
    """handlers/reports.py._format_month_uz() bilan AYNAN BIR XIL: 'YYYY-MM'
    ni 'Iyul 2026' ko'rinishiga o'tkazadi."""
    try:
        year, month = month_key.split("-")
        return f"{_UZ_MONTHS.get(month, month)} {year}"
    except ValueError:
        return month_key


async def api_reports_forecast(request: web.Request):
    """GET /api/webapp/reports/forecast - so'nggi 6 oylik savdo/foyda
    tarixi + (agar kamida bitta TO'LIQ tugagan oy bo'lsa) keyingi oy uchun
    oddiy o'rtachaga asoslangan prognoz (handlers/reports.py
    .monthly_forecast_report() bilan bir xil)."""
    auth, err = await _require_shop_auth(request)
    if err:
        return err
    shop_id = auth["shop_id"]

    history = await db.get_monthly_profit_history(shop_id, months=6)
    forecast = await db.get_profit_forecast(shop_id)

    return web.json_response({
        "history": [
            {"month": h["month"], "month_label": _format_month_uz(h["month"]),
             "sales_count": h["sales_count"], "profit": h["profit"]}
            for h in history
        ],
        "has_data": any(h["sales_count"] for h in history),
        "forecast": {
            "forecast_month": forecast["forecast_month"],
            "forecast_month_label": _format_month_uz(forecast["forecast_month"]),
            "based_on_months": forecast["based_on_months"],
            "forecast_profit": forecast["forecast_profit"],
            "avg_sales_total": forecast["avg_sales_total"],
        } if forecast else None,
    })


def _compute_trend(series: list) -> list:
    """handlers/reports.py._compute_trend() bilan AYNAN BIR XIL: har bir
    davr uchun OLDINGI davrga nisbatan o'zgarish foizini qo'shadi."""
    result = []
    prev_value = None
    for item in series:
        value = item["value"]
        change_percent = None
        if prev_value is not None and prev_value != 0:
            change_percent = (value - prev_value) / prev_value * 100
        result.append({**item, "change_percent": change_percent})
        prev_value = value
    return result


async def api_reports_trend(request: web.Request):
    """GET /api/webapp/reports/trend - foydaning OY (so'nggi 6 oy) va
    HAFTA (so'nggi 8 hafta) kesimida qanday o'zgarib borayotgani, har
    birida oldingi davrga nisbatan foiz bilan (handlers/reports.py
    .trend_analysis_report() bilan bir xil)."""
    auth, err = await _require_shop_auth(request)
    if err:
        return err
    shop_id = auth["shop_id"]

    monthly = await db.get_monthly_profit_history(shop_id, months=6)
    weekly = await db.get_weekly_profit_history(shop_id, weeks=8)
    has_data = any(h["sales_count"] for h in monthly)

    monthly_series = [{"label": _format_month_uz(h["month"]), "value": h["profit"]} for h in monthly]
    weekly_series = [
        {
            "label": (
                f"{datetime.strptime(h['week_start'], '%Y-%m-%d').strftime('%d.%m')}–"
                f"{datetime.strptime(h['week_end'], '%Y-%m-%d').strftime('%d.%m')}"
            ),
            "value": h["profit"],
        }
        for h in weekly
    ]

    return web.json_response({
        "has_data": has_data,
        "monthly": _compute_trend(monthly_series) if has_data else [],
        "weekly": _compute_trend(weekly_series) if has_data else [],
    })


# ---------- 🏆 TOP MAHSULOTLAR ----------

async def api_reports_top_products(request: web.Request):
    """GET /api/webapp/reports/top-products?branch_id=<ixtiyoriy> - top 10
    eng ko'p sotilgan + top 10 eng ko'p foyda keltirgan (handlers/reports.py
    .top_products_show() bilan bir xil, faqat ikkalasi BITTA so'rovda)."""
    auth, err = await _require_shop_auth(request)
    if err:
        return err
    shop_id = auth["shop_id"]
    branch_id = _parse_branch_id(request)

    if branch_id:
        branch = await db.get_branch(shop_id, branch_id)
        if not branch:
            return web.json_response({"error": "branch_not_found"}, status=404)

    top_selling = await db.get_top_selling_products(shop_id, limit=10, branch_id=branch_id)
    top_profit = await db.get_top_profit_products(shop_id, limit=10, branch_id=branch_id)

    return web.json_response({
        "branch_id": branch_id,
        "top_selling": top_selling,
        "top_profit": top_profit,
    })


# ---------- 🔔 KUNLIK HISOBOT / 🚨 SHUBHALI HOLATLAR (yoqish/o'chirish) ----------

async def api_reports_daily_report_get(request: web.Request):
    auth, err = await _require_shop_auth(request)
    if err:
        return err
    enabled = await db.get_daily_report_enabled(auth["shop_id"])
    return web.json_response({"enabled": enabled})


async def api_reports_daily_report_set(request: web.Request):
    auth, err = await _require_shop_auth(request)
    if err:
        return err
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid_json"}, status=400)

    enabled = bool(body.get("enabled"))
    await db.set_daily_report_enabled(auth["shop_id"], enabled)
    return web.json_response({"enabled": enabled})


async def api_reports_suspicious_alert_get(request: web.Request):
    auth, err = await _require_shop_auth(request)
    if err:
        return err
    enabled = await db.get_suspicious_alert_enabled(auth["shop_id"])
    return web.json_response({"enabled": enabled})


async def api_reports_suspicious_alert_set(request: web.Request):
    auth, err = await _require_shop_auth(request)
    if err:
        return err
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid_json"}, status=400)

    enabled = bool(body.get("enabled"))
    await db.set_suspicious_alert_enabled(auth["shop_id"], enabled)
    return web.json_response({"enabled": enabled})


# ---------- 🗂 AUDIT JURNALI ----------

async def api_reports_audit_log(request: web.Request):
    """GET /api/webapp/reports/audit-log?limit=30 - eng oxirgi amallar,
    yangisidan boshlab (handlers/reports.py.audit_journal() bilan bir xil,
    lekin standart chegara Excel eksportdagidek emas, bot xabaridagidek 30 -
    ro'yxat ekranida cheksiz uzun bo'lib ketmasligi uchun)."""
    auth, err = await _require_shop_auth(request)
    if err:
        return err

    try:
        limit = int(request.query.get("limit", 30))
        limit = max(1, min(limit, 200))
    except (TypeError, ValueError):
        limit = 30

    rows = await db.get_audit_log(auth["shop_id"], limit=limit)
    return web.json_response({"logs": rows})


def register_routes(app: web.Application) -> None:
    """webapp.py'ning create_web_app() ichidan chaqiriladi - shu
    modulning barcha route'larini bitta joyda ro'yxatdan o'tkazadi."""
    app.router.add_get("/api/webapp/reports/summary", api_reports_summary)
    app.router.add_get("/api/webapp/reports/branches-comparison", api_reports_branches_comparison)
    app.router.add_get("/api/webapp/reports/sellers-comparison", api_reports_sellers_comparison)
    app.router.add_get("/api/webapp/reports/forecast", api_reports_forecast)
    app.router.add_get("/api/webapp/reports/trend", api_reports_trend)
    app.router.add_get("/api/webapp/reports/top-products", api_reports_top_products)
    app.router.add_get("/api/webapp/reports/daily-report", api_reports_daily_report_get)
    app.router.add_post("/api/webapp/reports/daily-report", api_reports_daily_report_set)
    app.router.add_get("/api/webapp/reports/suspicious-alert", api_reports_suspicious_alert_get)
    app.router.add_post("/api/webapp/reports/suspicious-alert", api_reports_suspicious_alert_set)
    app.router.add_get("/api/webapp/reports/audit-log", api_reports_audit_log)
