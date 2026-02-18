import asyncio
import sys
import time
from pathlib import Path
from aiohttp import web
from app.config import load_config, logger
from app.bot import setup_bot

async def health_server(port):
    async def handle(request): return web.Response(text="OK")
    app = web.Application()
    app.router.add_get("/", handle)
    app.router.add_get("/health", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", port).start()
    logger.info(f"Health server on port {port}")

async def auto_cleanup_task(temp_dir):
    """Background task to delete temp files older than 30 minutes."""
    while True:
        try:
            now = time.time()
            count = 0
            t_path = Path(temp_dir)
            if t_path.exists():
                for item in t_path.iterdir():
                    if item.is_file() and (now - item.stat().st_mtime) > 1800:
                        item.unlink()
                        count += 1
            if count > 0: logger.info(f"Auto-cleanup: Removed {count} old files")
        except Exception as e: logger.error(f"Cleanup error: {e}")
        await asyncio.sleep(600) # Run every 10 mins

async def main():
    logger.info("Starting FileForge Bot...")
    config = load_config()
    bot, dp, db, fm = await setup_bot(config)

    try: await bot.delete_webhook(drop_pending_updates=True)
    except: pass

    # Start health server and auto-cleanup
    asyncio.create_task(health_server(config.port))
    asyncio.create_task(auto_cleanup_task(config.temp_dir))

    try:
        logger.info("Polling started...")
        await dp.start_polling(bot, allowed_updates=["message", "callback_query"], drop_pending_updates=True)
    except Exception as e: logger.critical(f"Polling error: {e}")
    finally:
        fm.cleanup_all()
        await db.disconnect()
        await bot.session.close()
        logger.info("Shutdown complete.")

if __name__ == "__main__":
    try: asyncio.run(main())
    except: sys.exit(0)
