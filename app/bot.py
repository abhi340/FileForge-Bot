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
    user_cmds = [
        BotCommand(command="start", description="🚀 Start bot"),
        BotCommand(command="help", description="📖 How to use"),
        BotCommand(command="my_usage", description="📊 Check my usage"),
        BotCommand(command="myid", description="🆔 Get my ID")
    ]
    admin_cmds = user_cmds + [
        BotCommand(command="stats", description="📊 Global Stats"),
        BotCommand(command="list_users", description="📋 All Users"),
        BotCommand(command="broadcast", description="📢 Message All"),
        BotCommand(command="system_health", description="🏥 Health")
    ]
    await bot.set_my_commands(user_cmds, scope=BotCommandScopeDefault())
    await bot.set_my_commands(admin_cmds, scope=BotCommandScopeChat(chat_id=admin_id))

async def setup_bot(config):
    db = Database(config.turso_url, config.turso_token)
    await db.connect()
    whitelist = WhitelistRepo(db); usage = UsageRepo(db); system = SystemRepo(db)
    admin_svc = AdminService(whitelist, usage, system); fm = FileManager(config.temp_dir)
    await admin_svc.record_start()
    bot = Bot(token=config.token); dp = Dispatcher()
    await set_bot_commands(bot, config.admin_id)
    dp.message.middleware(AccessMiddleware(config, whitelist, system))
    dp.callback_query.middleware(AccessMiddleware(config, whitelist, system))

    main_rt = Router(name="main")
    @main_rt.message(Command("start"))
    async def cmd_start(m: Message):
        await m.reply(f"👋 Welcome to FileForge Bot!{' 👑' if m.from_user.id == config.admin_id else ''}\n"
                      "Send me a file (Image, PDF, DOCX) to begin.\nUse /help for tools list.")

    @main_rt.message(Command("my_usage"))
    async def cmd_usage(m: Message):
        user = await whitelist.get_user(m.from_user.id)
        if not user: return
        today = await usage.user_today(m.from_user.id)
        total = await usage.user_total(m.from_user.id)
        await m.reply(f"📊 **Your Usage Stats**\n━━━━━━━━━━━━━━\n"
                      f"📅 Today: `{today} / {user['daily_limit']}`\n"
                      f"📁 Total Files: `{total}`\n"
                      f"✨ Status: `{'Active' if not user['is_suspended'] else 'Suspended'}`")

    @main_rt.message(Command("help"))
    async def cmd_help(m: Message):
        await m.reply("📖 **How to use:**\n1. Send file\n2. Select tool\n3. Wait for result\n\n"
                      "🖼 **Image:** OCR, Compress, Resize, Convert, Blur, PDF, ID-Photo\n"
                      "📄 **PDF:** Merge, Protect, Split, Compress, Text/Image Extract\n"
                      "📝 **Word:** Convert to PDF, Text/Image Extract, Word Count")

    @main_rt.message(Command("myid"))
    async def cmd_id(m: Message): await m.reply(f"🆔 Your ID: `{m.from_user.id}`")

    register_admin_handlers(Router(name="admin"), config, admin_svc, bot)
    register_file_handlers(Router(name="files"), config, fm, usage, bot)
    dp.include_router(main_rt); dp.include_router(admin_rt); dp.include_router(file_rt)
    return bot, dp, db, fm
