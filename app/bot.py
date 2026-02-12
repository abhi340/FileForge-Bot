"""
Bot assembly — wires everything together.
"""

from aiogram import Bot, Dispatcher, Router
from aiogram.types import Message
from aiogram.filters import Command

from app.config import BotConfig, logger
from app.database import Database, WhitelistRepo, UsageRepo, SystemRepo
from app.middleware import AccessMiddleware
from app.admin import AdminService, register_admin_handlers
from app.file_router import register_file_handlers
from app.file_manager import FileManager


async def setup_bot(config: BotConfig) -> tuple:
    """Setup and return (bot, dispatcher, database, file_manager)."""

    # Database
    db = Database(config.database_path)
    await db.connect()

    # Repos
    whitelist = WhitelistRepo(db)
    usage = UsageRepo(db)
    system = SystemRepo(db)

    # Services
    admin_svc = AdminService(whitelist, usage, system)
    fm = FileManager(config.temp_dir)

    await admin_svc.record_start()

    # Bot & Dispatcher
    bot = Bot(token=config.token)
    dp = Dispatcher()

    # Middleware
    dp.message.middleware(AccessMiddleware(config, whitelist, system))
    dp.callback_query.middleware(AccessMiddleware(config, whitelist, system))

    # ── Main commands router ──
    main_rt = Router(name="main")

    @main_rt.message(Command("start"))
    async def cmd_start(message: Message) -> None:
        is_admin = message.from_user.id == config.admin_id
        badge = " 👑" if is_admin else ""
        await message.reply(
            f"👋 **Welcome to File Utility Bot!**{badge}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Send me a file and choose what to do.\n\n"
            f"**Supported:**\n"
            f"🖼 Images — metadata, resize, convert\n"
            f"📄 PDF — metadata, text, images, split\n"
            f"📝 DOCX — metadata, comments, text\n\n"
            f"📏 Max size: {config.max_file_size_mb}MB\n\n"
            f"Use /help for details.",
            parse_mode="Markdown",
        )

    @main_rt.message(Command("help"))
    async def cmd_help(message: Message) -> None:
        await message.reply(
            "📖 **How to use:**\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "1️⃣ Send a file\n"
            "2️⃣ Choose an operation\n"
            "3️⃣ Get your result!\n\n"
            "**🖼 Image Tools:**\n"
            "• Remove metadata\n"
            "• Resize (50% / 25%)\n"
            "• Convert (PNG/JPG/WEBP)\n\n"
            "**📄 PDF Tools:**\n"
            "• Remove metadata\n"
            "• Extract text\n"
            "• Extract images\n"
            "• Split pages\n\n"
            "**📝 DOCX Tools:**\n"
            "• Remove metadata\n"
            "• Remove comments\n"
            "• Extract text",
            parse_mode="Markdown",
        )

    @main_rt.message(Command("myid"))
    async def cmd_myid(message: Message) -> None:
        await message.reply(
            f"🆔 Your ID: `{message.from_user.id}`",
            parse_mode="Markdown",
        )

    # ── Admin router ──
    admin_rt = Router(name="admin")
    register_admin_handlers(admin_rt, config, admin_svc, bot)

    # ── File router ──
    file_rt = Router(name="files")
    register_file_handlers(file_rt, config, fm, usage, bot)

    # Include routers (order matters)
    dp.include_router(admin_rt)
    dp.include_router(main_rt)
    dp.include_router(file_rt)

    logger.info("Bot setup complete")
    return bot, dp, db, fm
