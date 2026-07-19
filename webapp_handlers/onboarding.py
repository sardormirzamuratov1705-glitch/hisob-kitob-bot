"""RO'YXATDAN O'TISH / TAKLIF HAVOLASI - MINI APP (8-BLOK, 15-BOSQICH).

Bu modul do'kon egasi Mini App'dagi "Sotuvchilar" bo'limi orqali yangi
sotuvchi uchun bir martalik taklif havolasi (link) yasay olishi uchun
REST API endpointini o'z ichiga oladi.

MUHIM - BIR XILLIK: handlers/sellers.py dagi "🔗 Sotuvchi uchun link"
tugmasi (create_seller_invite_link()) bilan AYNAN BIR XIL
db.create_seller_invite() funksiyasidan va link formatidan
(https://t.me/<bot_username>?start=seller_<token>) foydalanadi - link
bosilgach ishlaydigan qabul qilish mantig'i ham (handlers/start.py dagi
"seller_" prefiksli deep-link) O'ZGARTIRILMAGAN, shu sababli mini
app'da yasalgan link ham bot orqali yasalgandek ishlaydi.

DIQQAT - BOSHQA "RO'YXATDAN O'TISH" YO'LLARI HAQIDA: quyidagilar bu
modulga KIRMAYDI, chunki ALLAQACHON boshqa joyda (11-bosqich, bosh
admin paneli - webapp.py) amalga oshirilgan:
- Bosh adminning YANGI DO'KON EGASI uchun taklif havolasi
  (api_admin_owner_invite_link, webapp.py).
- Bosh adminning YANGI BOSH ADMIN uchun taklif havolasi
  (api_admin_admins_invite_link, webapp.py).
Shuningdek, notanish (hali bazada umuman yo'q) odamning Mini App'ni
o'zi ochishi (landing/self-register) REJA DOIRASIDAN TASHQARIDA
qoladi - Mini App faqat botga ulangan Telegram tugmasi orqali
ochiladi, shu sababli uni ochgan kishi allaqachon bazada bo'lishi
kerak (aks holda webapp._authenticate 401 qaytaradi - bu ataylab
shunday, xavfsizlik uchun).

KIM FOYDALANA OLADI: FAQAT haqiqiy do'kon egasi (bot tarafidagi
_require_owner() bilan bir xil - sotuvchi o'zi yangi sotuvchi taklif
qila olmaydi).
"""

import logging

from aiohttp import web

import access_control
import database as db

logger = logging.getLogger(__name__)


async def _require_owner_auth(request: web.Request):
    """webapp_handlers/sellers.py dagi bir xil nomli funksiya bilan AYNAN
    BIR XIL (aylanma import haqidagi izoh ham o'sha yerdagi bilan bir xil
    sabab)."""
    from webapp import _authenticate

    auth = await _authenticate(request)
    if not auth:
        return None, web.json_response({"error": "unauthorized"}, status=401)
    if auth["role"] != "owner":
        return None, web.json_response({"error": "not_applicable"}, status=404)
    return auth, None


async def api_onboarding_seller_invite(request: web.Request):
    """POST /api/webapp/onboarding/seller-invite - joriy do'kon egasi
    uchun yangi bir martalik sotuvchi taklif havolasini yasaydi (joriy
    tanlangan filialga biriktiriladi - handlers/sellers.py dagi bilan
    bir xil)."""
    auth, err = await _require_owner_auth(request)
    if err:
        return err
    shop_id = auth["shop_id"]

    branch_id = await access_control.get_branch_id(shop_id)
    token = await db.create_seller_invite(shop_id, auth["telegram_id"], branch_id=branch_id)

    bot = request.app["bot"]
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=seller_{token}"

    return web.json_response({"link": link})


def register_routes(app: web.Application) -> None:
    """webapp.py'ning create_web_app() ichidan chaqiriladi - shu
    modulning barcha route'larini bitta joyda ro'yxatdan o'tkazadi."""
    app.router.add_post("/api/webapp/onboarding/seller-invite", api_onboarding_seller_invite)
