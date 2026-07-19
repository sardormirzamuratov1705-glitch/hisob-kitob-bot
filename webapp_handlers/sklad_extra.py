"""SKLAD QO'SHIMCHALARI - MINI APP (9-BLOK, 18-BOSQICH: BACKEND).

Bu modul "Sklad" bo'limiga ikkita YETISHMAYOTGAN imkoniyatni qo'shadi:

1) 🤖 AI BUYURTMA TAVSIYASI - bot tarafida ("🤖 AI buyurtma tavsiyasi"
   tugmasi, handlers/products.py) allaqachon bor bo'lgan hisoblashning
   (oxirgi 30 kunlik sotilish tezligi + yetkazib berish muddati asosida,
   qaysi mahsulot tezroq tugab qolishi mumkinligini aniqlash) mini
   app'dagi ko'rinishi - shu bilan foydalanuvchi botga o'tmasdan, veb-
   ilovaning o'zida shoshilinch buyurtma kerak bo'lgan tovarlarni ko'ra
   oladi.

2) 📢 KANAL POSTI - bot tarafida yangi mahsulot RASM bilan yaratilganda
   avtomatik kanalga post qilinadi va miqdor o'zgarganda o'sha post
   YANGILANADI (edit_message_caption). Mini App orqali yaratilgan
   mahsulotda esa RASM YO'Q (veb-ilova hozircha rasm yuklashni qo'llab-
   quvvatlamaydi) - shu sababli bu yerda MATNLI (rasmsiz) post
   yasaladi. MUHIM: matnli xabarda "caption" emas, oddiy "text" bo'ladi,
   shuning uchun uni keyinchalik yangilashda edit_message_caption()
   ISHLAMAYDI (Telegram xato qaytaradi) - shu sabab sync_channel_post()
   AVVAL caption'ni tahrirlashga urinadi (bot tarafida RASM bilan
   yaratilgan eski mahsulotlar uchun), muvaffaqiyatsiz bo'lsa
   edit_message_text()ga o'tadi (veb-ilovada yaratilgan, rasmsiz
   mahsulotlar uchun) - shu orqali IKKALA turdagi post ham to'g'ri
   yangilanadi.

MUHIM - BIR XILLIK: AI tavsiya hisobi xuddi handlers/products.py
(bot tarafi)dagi bilan AYNAN BIR XIL database.py funksiyalaridan
(db.get_restock_lead_time_days / db.get_ai_restock_suggestions)
foydalanadi - shu sababli ikkala tarafda ham natija bir xil bo'ladi.
Reja qoidasiga ko'ra ("hech bir bosqich handlers/*.py'ga tegmaydi")
handlers/products.py'ga tegilmadi - AI hisoblash mantig'i database.py'da
ALLAQACHON umumiy funksiya sifatida borligi uchun bu yerda hech narsani
qaytadan yozishga hojat yo'q, shunchaki chaqiriladi."""

import logging

from aiohttp import web

import config

logger = logging.getLogger(__name__)


async def _require_shop_auth(request: web.Request):
    """webapp._authenticate orqali autentifikatsiya qiladi va do'kon
    egasi YOKI sotuvchiga (lekin bosh adminga EMAS) ruxsat beradi - xuddi
    webapp_handlers/debts.py'dagi bir xil nomli funksiya kabi (aylanma
    import haqidagi izoh ham o'sha yerdagi bilan bir xil sabab): "Sklad"
    bo'limi bot tarafida ham ega va sotuvchiga bir xil ochiq."""
    from webapp import _authenticate

    auth = await _authenticate(request)
    if not auth:
        return None, web.json_response({"error": "unauthorized"}, status=401)
    return auth, None


async def api_ai_restock_suggestions(request: web.Request):
    """GET /api/webapp/sklad/ai-suggestions - "🤖 AI buyurtma tavsiyasi"
    bo'limining Mini App'dagi ko'rinishi (qarang: modul boshidagi izoh)."""
    auth, err = await _require_shop_auth(request)
    if err:
        return err

    payload = await get_ai_restock_suggestions_payload(auth["shop_id"])
    return web.json_response(payload)


def register_routes(app: web.Application) -> None:
    """webapp.py'ning create_web_app() ichidan chaqiriladi - shu
    modulning route'ini ro'yxatdan o'tkazadi (kanal-bilan-bog'liq
    funksiyalar - post_new_product_to_channel/sync_channel_post_quantity -
    route emas, oddiy Python funksiyalari: ular webapp.py'dagi MAVJUD
    api_sklad_create_product/api_sklad_add_quantity handlerlaridan
    to'g'ridan-to'g'ri chaqiriladi, qarang: webapp.py)."""
    app.router.add_get("/api/webapp/sklad/ai-suggestions", api_ai_restock_suggestions)


async def get_ai_restock_suggestions_payload(shop_id: int) -> dict:
    """GET /api/webapp/sklad/ai-suggestions uchun tayyor JSON-ga mos dict
    qaytaradi. webapp.py'dagi route handler avtentifikatsiyadan keyin
    shu funksiyani chaqiradi (aylanma import bo'lmasin uchun _authenticate
    shu modulga emas, webapp.py'ning o'zida qoladi)."""
    import database as db

    lead_time = await db.get_restock_lead_time_days(shop_id)
    suggestions = await db.get_ai_restock_suggestions(shop_id, lookback_days=30, lead_time_days=lead_time)

    items = []
    for s in suggestions:
        p = s["product"]
        days_left = max(s["days_left"], 0)
        if s["days_left"] <= 0:
            urgency = "high"
        elif s["days_left"] <= lead_time / 2:
            urgency = "medium"
        else:
            urgency = "low"
        items.append({
            "product_id": p["id"],
            "name": p["name"],
            "quantity": p["quantity"],
            "daily_sales_rate": s["daily_sales_rate"],
            "days_left": days_left,
            "suggested_qty": s["suggested_qty"],
            "urgency": urgency,
        })

    return {"lead_time_days": lead_time, "lookback_days": 30, "suggestions": items}


async def post_new_product_to_channel(bot, name: str, price: float, sell_price, quantity: float):
    """Mini App orqali yaratilgan (RASMSIZ) yangi mahsulot uchun kanalga
    MATNLI e'lon yuboradi (bot tarafidagi rasm bilan postlashdan farqli -
    qarang: modul boshidagi izoh). CHANNEL_ID sozlanmagan bo'lsa yoki
    yuborishda xato bo'lsa - jim None qaytaradi (mahsulot yaratish
    baribir davom etaveradi, kanal - qo'shimcha imkoniyat, majburiy emas)."""
    if not config.CHANNEL_ID:
        return None
    display_price = sell_price if sell_price else price
    try:
        sent = await bot.send_message(
            config.CHANNEL_ID,
            f"🆕 {name} | Savdo narxi: {display_price:.0f} so'm | {quantity:.0f} dona\n"
            f"<i>(Veb-ilova orqali qo'shildi)</i>",
        )
        return sent.message_id
    except Exception as e:
        logger.warning(f"WebApp: yangi mahsulotni kanalga yuborib bo'lmadi: {e}")
        return None


async def sync_channel_post_quantity(bot, product: dict, new_quantity: float) -> None:
    """Mini App orqali miqdor o'zgarganda (Skladga qo'shish/kamaytirish)
    kanaldagi postni yangilaydi - bot tarafidagi
    handlers/sales.py:perform_sale_transaction() bilan BIR XIL vazifa,
    lekin IKKALA post turini (rasmli/matnli) qo'llab-quvvatlaydi (qarang:
    modul boshidagi izoh)."""
    if not product.get("channel_message_id") or not config.CHANNEL_ID:
        return

    text = f"📦 {product['name']} | {new_quantity:.0f} dona qoldi"
    try:
        await bot.edit_message_caption(
            chat_id=config.CHANNEL_ID,
            message_id=product["channel_message_id"],
            caption=text,
        )
        return
    except Exception:
        pass  # Rasmli post emas ekan (yoki boshqa vaqtinchalik xato) - matn sifatida sinab ko'ramiz.

    try:
        await bot.edit_message_text(
            chat_id=config.CHANNEL_ID,
            message_id=product["channel_message_id"],
            text=text,
        )
    except Exception as e:
        logger.warning(f"WebApp: kanaldagi postni yangilab bo'lmadi: {e}")
