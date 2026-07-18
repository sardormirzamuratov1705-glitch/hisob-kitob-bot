import asyncio
import html
import logging
import traceback
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import ErrorEvent

import config
import database as db
import alerts
import access_control
from access_control import OwnerOnlyMiddleware
from fsm_storage import SQLiteStorage
from handlers import start, products, sales, transactions, debts, reports, users, sellers, branches, subscription
import webapp


async def notify_admins_error(bot: Bot, context: str, exc: Exception):
    """1-BOSQICH: istalgan joyda (update ichida ham, fon tsikllarida ham)
    yuz bergan xato haqida ADMIN_IDS'dagi barcha adminlarga Telegram orqali
    xabar yuboradi. Adminga xabar yuborishning o'zi xato bersa - bu botning
    asosiy ishlashiga ta'sir qilmaydi, faqat logga yoziladi."""
    if not config.ADMIN_IDS:
        return
    text = (
        "‼️ <b>Botda kutilmagan xato yuz berdi</b>\n\n"
        f"<b>Joy:</b> {html.escape(context)}\n"
        f"<b>Xato:</b> <code>{html.escape(str(exc))}</code>"
    )
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text)
        except Exception as notify_error:
            logging.warning(f"Adminga ({admin_id}) xato haqida xabar yuborib bo'lmadi: {notify_error}")


async def _debt_reminder_loop(bot: Bot):
    """Har 24 soatda bir marta ishga tushadi - har bir do'kon egasiga FAQAT
    o'ZINING muddati o'tgan qarzlari haqida xabar yuboradi
    (alerts.send_debt_reminders do'konlar bo'yicha alohida-alohida ishlaydi).
    Bot tez-tez qayta ishga tushsa (masalan har redeployda) ham, bugun
    allaqachon yuborilgan bo'lsa qaytadan yubormaydi - buning uchun oxirgi
    yuborilgan SANA settings jadvalida saqlanadi."""
    while True:
        today = config.now().strftime("%Y-%m-%d")
        last_sent = await db.get_setting("debt_reminder_last_sent", "")
        if last_sent != today:
            try:
                await alerts.send_debt_reminders(bot)
                await db.set_setting("debt_reminder_last_sent", today)
            except Exception as e:
                logging.warning(f"Qarz eslatmasi tsiklida xato: {e}")
                await notify_admins_error(bot, "Qarz eslatmasi tsikli", e)
        await asyncio.sleep(24 * 60 * 60)


async def _subscription_reminder_loop(bot: Bot):
    """8-BOSQICH: Har 24 soatda bir marta ishga tushadi - har bir do'kon
    egasiga o'zining obuna muddati tugashiga 7/3/0 kun qolganda avtomatik
    eslatma yuboradi (alerts.send_subscription_reminders). Bot tez-tez qayta
    ishga tushsa (masalan har redeployda) ham, bugun allaqachon yuborilgan
    bo'lsa qaytadan yubormaydi (debt reminder loop bilan bir xil mantiq)."""
    while True:
        today = config.now().strftime("%Y-%m-%d")
        last_sent = await db.get_setting("subscription_reminder_last_sent", "")
        if last_sent != today:
            try:
                await alerts.send_subscription_reminders(bot)
                await db.set_setting("subscription_reminder_last_sent", today)
            except Exception as e:
                logging.warning(f"Obuna eslatmasi tsiklida xato: {e}")
                await notify_admins_error(bot, "Obuna eslatmasi tsikli", e)
        await asyncio.sleep(24 * 60 * 60)


async def _daily_report_loop(bot: Bot):
    """6-BOSQICH: yuqoridagi ikkita sikldan farqli - bular "bot ishga
    tushgandan 24 soat keyin" ishlaydi, lekin kunlik hisobot ANIQ bir vaqtda
    (config.DAILY_REPORT_HOUR:DAILY_REPORT_MINUTE, masalan har kuni 21:00)
    yuborilishi kerak, shuning uchun har safar "keyingi shu vaqt"gacha
    qancha qolganini hisoblab, aynan shuncha kutadi (drift yig'ilib
    qolmasligi uchun har iteratsiyada qaytadan hisoblanadi)."""
    while True:
        now = config.now()
        target = now.replace(
            hour=config.DAILY_REPORT_HOUR, minute=config.DAILY_REPORT_MINUTE,
            second=0, microsecond=0,
        )
        if target <= now:
            target += timedelta(days=1)
        await asyncio.sleep((target - now).total_seconds())
        try:
            await alerts.send_daily_reports_to_all(bot)
        except Exception as e:
            logging.warning(f"Kunlik hisobot tsiklida xato: {e}")
            await notify_admins_error(bot, "Kunlik hisobot tsikli", e)


def _make_error_handler(bot: Bot):
    """1-BOSQICH: hech qaysi handler ushlamagan (kutilmagan) xatoni ushlaydi.
    Avvalgidek serverning logiga yozadi, LEKIN endi qo'shimcha ravishda
    ADMIN_IDS'dagi har bir adminga ham Telegram xabar ko'rinishida yuboradi -
    shunda bot "jimgina" ishlamay qolsa ham, admin buni darhol biladi.
    Adminga xabar yuborishning o'zi xato bersa (masalan admin botni
    bloklagan) - bu botning ishlashiga umuman ta'sir qilmaydi, faqat logga
    yoziladi."""

    async def on_error(event: ErrorEvent):
        logging.exception("Kutilmagan xato:", exc_info=event.exception)

        if not config.ADMIN_IDS:
            return

        tb_text = "".join(traceback.format_exception(
            type(event.exception), event.exception, event.exception.__traceback__,
        ))
        update_text = ""
        try:
            if event.update:
                update_text = f"\n\n<b>Update:</b>\n<code>{html.escape(event.update.model_dump_json(exclude_none=True))[:500]}</code>"
        except Exception:
            pass

        text = (
            "‼️ <b>Botda kutilmagan xato yuz berdi</b>\n\n"
            f"<b>Xato:</b> <code>{html.escape(str(event.exception))}</code>"
            f"{update_text}\n\n"
            f"<b>Traceback (oxiri):</b>\n<code>{html.escape(tb_text[-2000:])}</code>"
        )
        if len(text) > 4000:
            text = text[:4000] + "\n…"

        for admin_id in config.ADMIN_IDS:
            try:
                await bot.send_message(admin_id, text)
            except Exception as notify_error:
                logging.warning(f"Adminga ({admin_id}) xato haqida xabar yuborib bo'lmadi: {notify_error}")

    return on_error


async def on_startup(bot: Bot):
    await db.init_db()
    await access_control.load_extra_admins()
    asyncio.create_task(_debt_reminder_loop(bot))
    asyncio.create_task(_subscription_reminder_loop(bot))
    asyncio.create_task(_daily_report_loop(bot))
    if config.WEBHOOK_HOST:
        await bot.set_webhook(config.WEBHOOK_URL, drop_pending_updates=True)
        logging.info(f"Webhook o'rnatildi: {config.WEBHOOK_URL}")
    else:
        await bot.delete_webhook(drop_pending_updates=True)
        logging.info("Polling rejimida ishga tushdi (WEBHOOK_HOST sozlanmagan).")


async def on_shutdown(bot: Bot):
    if config.WEBHOOK_HOST:
        await bot.delete_webhook()


async def _run_polling_and_webserver(dp: Dispatcher, bot: Bot, app):
    """POLLING rejimida ham (WEBHOOK_HOST sozlanmagan bo'lsa) veb-server
    (WebApp statik fayllari + API) PARALLEL ishga tushishi kerak - aks holda
    "🛒 Savdo" WebApp tugmasi ochiladigan HTTPS manzil umuman ishlamay qoladi.
    Shuning uchun ikkalasi ham (bot polling VA aiohttp server) bitta asyncio
    tsiklida, bir-biriga xalal bermay, parallel ishlaydi."""
    from aiohttp import web as aiohttp_web

    runner = aiohttp_web.AppRunner(app)
    await runner.setup()
    site = aiohttp_web.TCPSite(runner, host="0.0.0.0", port=config.PORT)
    await site.start()
    logging.info(f"Veb-server (WebApp/API) {config.PORT}-portda ishga tushdi.")

    try:
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()


def main():
    logging.basicConfig(level=logging.INFO)

    if not config.BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN topilmadi! Railway -> Settings -> Variables bo'limini tekshiring.")

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=SQLiteStorage(config.DB_PATH))

    dp.errors.register(_make_error_handler(bot))

    # MUHIM: botning barcha funksiyalari faqat bosh admin (ADMIN_IDS) va
    # bazaga qo'shilgan do'kon egalari uchun ochiq (access_control.is_authorized).
    # Bu yo'q bo'lsa, botni Telegram'da topgan yoki qarz eslatma linkini bosgan
    # HAR QANDAY odam Sklad/Kirim-Chiqim/Qarz daftar/Hisobot bo'limlariga kirib,
    # barcha ma'lumotlarni ko'rishi mumkin edi.
    dp.message.outer_middleware(OwnerOnlyMiddleware())
    dp.callback_query.outer_middleware(OwnerOnlyMiddleware())

    dp.include_router(start.router)
    dp.include_router(products.router)
    dp.include_router(sales.router)
    dp.include_router(transactions.router)
    dp.include_router(debts.router)
    dp.include_router(reports.router)
    dp.include_router(users.router)
    dp.include_router(sellers.router)
    dp.include_router(branches.router)
    dp.include_router(subscription.router)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # ---------- VEB-SERVER (WEB APP - 1-BOSQICH) ----------
    # WebApp statik fayllari (webapp_static/) va API (webapp.py) shu bitta
    # aiohttp ilovasida joylashadi - webhook rejimida bo'lsa, Telegram
    # webhook route'i ham AYNAN SHU ilovaga qo'shiladi (bitta port, bitta server).
    app = webapp.create_web_app(bot)

    if config.WEBHOOK_HOST:
        # ---------- WEBHOOK REJIMI ----------
        # Telegram xabarlarni o'zi bizga "itarib" beradi (push qiladi),
        # shuning uchun "Conflict: terminated by other getUpdates" xatosi
        # umuman bo'lmaydi - ikkita nusxa polling qilib to'qnashish xavfi yo'q.
        from aiohttp import web
        from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

        SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=config.WEBHOOK_PATH)
        setup_application(app, dp, bot=bot)
        web.run_app(app, host="0.0.0.0", port=config.PORT)
    else:
        # ---------- POLLING REJIMI (eski, zaxira) ----------
        # Endi bot polling qilayotganda ham veb-server (WebApp/API) PARALLEL
        # ishlaydi - shuning uchun oddiy asyncio.run(dp.start_polling(bot))
        # o'rniga ikkalasini birga ishga tushiradigan funksiya chaqiriladi.
        asyncio.run(_run_polling_and_webserver(dp, bot, app))


if __name__ == "__main__":
    main()
