import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

import config
import database as db
from handlers import start, products, sales, transactions, debts, reports


async def on_startup(bot: Bot):
    await db.init_db()
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

    dp.include_router(start.router)
    dp.include_router(products.router)
    dp.include_router(sales.router)
    dp.include_router(transactions.router)
    dp.include_router(debts.router)
    dp.include_router(reports.router)

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
