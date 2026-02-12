import asyncio
import sys

from aiohttp import web

from app.config import load_config, logger
from app.bot import setup_bot


async def health_server(port):
    async def handle(request):
        return web.Response(text="OK")

    app = web.Application()
    app.router.add_get("/", handle)
    app.router.add_get("/health", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Health server on port {port}")


async def main():
    logger.info("Starting File Utility Bot...")

    config = load_config()
    bot, dp, db, fm = await setup_bot(config)

    try:
        await health_server(config.port)
    except Exception as e:
        logger.warning(f"Health server failed: {e}")

    try:
        logger.info("Polling started...")
        await dp.start_polling(
            bot,
            allowed_updates=["message", "callback_query"],
            drop_pending_updates=True,
        )
    except Exception as e:
        logger.critical(f"Polling error: {e}")
    finally:
        fm.cleanup_all()
        await db.disconnect()
        await bot.session.close()
        logger.info("Shutdown complete.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted.")
    except Exception as e:
        logger.critical(f"Fatal: {e}")
        sys.exit(1)
