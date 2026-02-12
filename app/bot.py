from aiogram import Bot, Dispatcher, Router
from aiogram.types import Message, BotCommand, BotCommandScopeChat, BotCommandScopeDefault
from aiogram.filters import Command

from app.config import BotConfig, logger
from app.database import Database, WhitelistRepo, UsageRepo, SystemRepo
from app.middleware import AccessMiddleware
from app.admin import AdminService, register_admin_handlers
from app.file_router import register_file_handlers
from app.file_manager import FileManager


async def set_bot_commands(bot, admin_id):
    # Commands visible to ALL users
    user_commands = [
        BotCommand(command="start", description="Start the bot"),
        BotCommand(command="help", description="How to use"),
        BotCommand(command="myid", description="Get your Telegram ID"),
    ]

    # Commands visible ONLY to admin
    admin_commands = [
        BotCommand(command="start", description="Start the bot"),
        BotCommand(command="help", description="How to use"),
        BotCommand(command="myid", description="Get your Telegram ID"),
        BotCommand(command="add_user", description="Whitelist a user"),
        BotCommand(command="remove_user", description="Remove a user"),
        BotCommand(command="list_users", description="Show all users"),
        BotCommand(command="suspend_user", description="Suspend a user"),
        BotCommand(command="unsuspend_user", description="Unsuspend a user"),
        BotCommand(command="set_limit", description="Set daily limit"),
        BotCommand(command="stats", description="Global analytics"),
        BotCommand(command="user_stats", description="User analytics"),
        BotCommand(command="broadcast", description="Message all users"),
        BotCommand(command="maintenance_on", description="Enable maintenance"),
        BotCommand(command="maintenance_off", description="Disable maintenance"),
        BotCommand(command="system_health", description="System health"),
    ]

    # Set for all users
    await bot.set_my_commands(user_commands, scope=BotCommandScopeDefault())

    # Set for admin only
    await bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=admin_id))

    logger.info("Bot commands set (user + admin)")


async def setup_bot(config):
    db = Database(config.turso_url, config.turso_token)
    await db.connect()

    whitelist = WhitelistRepo(db)
    usage = UsageRepo(db)
    system = SystemRepo(db)

    admin_svc = AdminService(whitelist, usage, system)
    fm = FileManager(config.temp_dir)

    await admin_svc.record_start()

    bot = Bot(token=config.token)
    dp = Dispatcher()

    # Set different menus for users vs admin
    await set_bot_commands(bot, config.admin_id)

    dp.message.middleware(AccessMiddleware(config, whitelist, system))
    dp.callback_query.middleware(AccessMiddleware(config, whitelist, system))

    main_rt = Router(name="main")

    @main_rt.message(Command("start"))
    async def cmd_start(message: Message):
        is_admin = message.from_user.id == config.admin_id
        badge = " (Admin)" if is_admin else ""
        await message.reply(
            f"Welcome to File Utility Bot!{badge}\n\n"
            f"Send me a file and choose what to do.\n\n"
            f"Supported:\n"
            f"Images - metadata, resize, convert\n"
            f"PDF - metadata, text, images, split\n"
            f"DOCX - metadata, comments, text\n\n"
            f"Max size: {config.max_file_size_mb}MB\n\n"
            f"Use /help for details."
        )

    @main_rt.message(Command("help"))
    async def cmd_help(message: Message):
        await message.reply(
            "How to use:\n\n"
            "1. Send a file\n"
            "2. Choose an operation\n"
            "3. Get your result!\n\n"
            "Image Tools:\n"
            "- Remove metadata\n"
            "- Resize (50% / 25%)\n"
            "- Convert (PNG/JPG/WEBP)\n\n"
            "PDF Tools:\n"
            "- Remove metadata\n"
            "- Extract text\n"
            "- Extract images\n"
            "- Split pages\n\n"
            "DOCX Tools:\n"
            "- Remove metadata\n"
            "- Remove comments\n"
            "- Extract text"
        )

    @main_rt.message(Command("myid"))
    async def cmd_myid(message: Message):
        await message.reply(f"Your ID: {message.from_user.id}")

    admin_rt = Router(name="admin")
    register_admin_handlers(admin_rt, config, admin_svc, bot)

    file_rt = Router(name="files")
    register_file_handlers(file_rt, config, fm, usage, bot)

    dp.include_router(admin_rt)
    dp.include_router(main_rt)
    dp.include_router(file_rt)

    logger.info("Bot setup complete")
    return bot, dp, db, fm
