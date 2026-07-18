import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

import config
import database as db
import alerts
from access_control import OwnerOnlyMiddleware
from handlers import start, products, sales, transactions, debts, reports, users, sellers, branches, subscription


async def _debt_reminder_loop(bot: Bot):
    """Har 24 soatda bir marta ishga tushadi - har bir do'kon egasiga FAQAT
    o'ZINING muddati o'tgan qarzlari haqida xabar yuboradi
    (alerts.send_debt_reminders do'konlar bo'yicha alohida-alohida ishlaydi)."""
    while True:
        try:
            await alerts.send_debt_reminders(bot)
        except Exception as e:
            logging.warning(f"Qarz eslatmasi tsiklida xato: {e}")
        await asyncio.sleep(24 * 60 * 60)


async def _subscription_reminder_loop(bot: Bot):
    """8-BOSQICH: Har 24 soatda bir marta ishga tushadi - har bir do'kon
    egasiga o'zining obuna muddati tugashiga 7/3/0 kun qolganda avtomatik
    eslatma yuboradi (alerts.send_subscription_reminders)."""
    while True:
        try:
            await alerts.send_subscription_reminders(bot)
        except Exception as e:
            logging.warning(f"Obuna eslatmasi tsiklida xato: {e}")
        await asyncio.sleep(24 * 60 * 60)


async def _daily_report_loop(bot: Bot):
    """6-BOSQICH: yuqoridagi ikkita sikldan farqli - bular "bot ishga
    tushgandan 24 soat keyin" ishlaydi, lekin kunlik hisobot ANIQ bir vaqtda
    (config.DAILY_REPORT_HOUR:DAILY_REPORT_MINUTE, masalan har kuni 21:00)
    yuborilishi kerak, shuning uchun har safar "keyingi shu vaqt"gacha
    qancha qolganini hisoblab, aynan shuncha kutadi (drift yig'ilib
    qolmasligi uchun har iteratsiyada qaytadan hisoblanadi)."""
    while True:
        now = datetime.now()
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


async def on_startup(bot: Bot):
    await db.init_db()
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


def main():
    logging.basicConfig(level=logging.INFO)

    if not config.BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN topilmadi! Railway -> Settings -> Variables bo'limini tekshiring.")

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

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

    if config.WEBHOOK_HOST:
        # ---------- WEBHOOK REJIMI ----------
        # Telegram xabarlarni o'zi bizga "itarib" beradi (push qiladi),
        # shuning uchun "Conflict: terminated by other getUpdates" xatosi
        # umuman bo'lmaydi - ikkita nusxa polling qilib to'qnashish xavfi yo'q.
        from aiohttp import web
        from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

        app = web.Application()
        SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=config.WEBHOOK_PATH)
        setup_application(app, dp, bot=bot)
        web.run_app(app, host="0.0.0.0", port=config.PORT)
    else:
        # ---------- POLLING REJIMI (eski, zaxira) ----------
        asyncio.run(dp.start_polling(bot))


if __name__ == "__main__":
    main()
