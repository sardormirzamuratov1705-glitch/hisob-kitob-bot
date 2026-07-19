"""STATIK FAYLLAR (index.html/app.js/style.css) - MINI APP (20-BOSQICH: REFAKTORING).

Bu modul ilgari webapp.py ichida to'g'ridan-to'g'ri yozilgan edi.
20-bosqichda webapp.py'ni "barcha routerlarni yig'uvchi asosiy fayl"ga
aylantirish maqsadida BU YERGA ko'chirildi - XATTI-HARAKAT (kesh
headerlari, versiyalash) BUTUNLAY O'ZGARMADI, faqat joyi o'zgardi.
"""

import time
from pathlib import Path

from aiohttp import web

import config


def _no_cache_file_response(path: Path) -> web.FileResponse:
    """DIQQAT (KESH MUAMMOSI TUZATILDI): Telegram Desktop/mobil webview
    statik fayllarni (index.html/app.js/style.css) juda qattiq keshlab
    qo'yadi - shu sababli kod yangilab deploy qilingandan keyin ham
    foydalanuvchida ESKI app.js ishlab qolishi mumkin edi (masalan initData
    tuzatishi kabi muhim javob bermay qolganday tuyulishi). Shu headerlar
    orqali brauzer/webview har safar serverdan yangi nusxa so'rashga
    majburlanadi."""
    resp = web.FileResponse(path)
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


_STARTUP_VERSION = str(int(time.time()))


async def webapp_index(request: web.Request):
    """"/webapp" VA "/webapp/" - ikkalasi ham index.html'ni qaytaradi.

    DIQQAT (403 XATOSI TUZATILDI): avval bu yerda aiohttp'ning add_static()
    ishlatilgan edi - lekin aiohttp static route DIREKTORIYA so'ralganda
    (masalan "/webapp/") ICHIDAGI index.html'ni O'ZI QIDIRIB TOPMAYDI va
    show_index=False bo'lgani uchun "403 Forbidden" qaytaradi. Shu sababli
    endi har bir fayl uchun ANIQ (aniq nomi bilan) route beriladi - hech
    qanday noaniqlik/403 xavfi qolmaydi.

    DIQQAT (KESH MUAMMOSI TUZATILDI): app.js/style.css havolalariga
    ?v=<botning ishga tushgan vaqti> qo'shiladi - shunda Telegram
    Desktop'ning o'zi Cache-Control'ni e'tiborsiz qoldirsa ham, deploydan
    keyin bu havolalar "yangi URL" bo'lib qoladi va eski keshlangan
    app.js/style.css o'rniga har doim yangisi yuklanadi."""
    html = (Path(config.WEBAPP_STATIC_DIR) / "index.html").read_text(encoding="utf-8")
    html = html.replace('href="/webapp/style.css"', f'href="/webapp/style.css?v={_STARTUP_VERSION}"')
    html = html.replace('src="/webapp/app.js"', f'src="/webapp/app.js?v={_STARTUP_VERSION}"')
    resp = web.Response(text=html, content_type="text/html")
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


async def webapp_app_js(request: web.Request):
    return _no_cache_file_response(Path(config.WEBAPP_STATIC_DIR) / "app.js")


async def webapp_style_css(request: web.Request):
    return _no_cache_file_response(Path(config.WEBAPP_STATIC_DIR) / "style.css")


def register_routes(app: web.Application) -> None:
    """webapp.py'ning create_web_app() ichidan chaqiriladi. MUHIM: har bir
    statik fayl uchun ANIQ route (add_static() o'rniga, 403 Forbidden
    xatosining oldini olish uchun). Yangi statik fayl (masalan rasm)
    qo'shilsa, shu yerga yana bitta add_get qatori qo'shish kifoya."""
    app.router.add_get("/webapp", webapp_index)
    app.router.add_get("/webapp/", webapp_index)
    app.router.add_get("/webapp/app.js", webapp_app_js)
    app.router.add_get("/webapp/style.css", webapp_style_css)
