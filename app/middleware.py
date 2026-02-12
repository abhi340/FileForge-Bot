from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject

from app.config import BotConfig, logger
from app.database import WhitelistRepo, SystemRepo


class AccessMiddleware(BaseMiddleware):
    def __init__(self, config, whitelist, system):
        self.config = config
        self.whitelist = whitelist
        self.system = system
        super().__init__()

    async def __call__(self, handler, event, data):
        user_id = None
        if isinstance(event, Message) and event.from_user:
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            user_id = event.from_user.id

        if user_id is None:
            return

        if user_id == self.config.admin_id:
            return await handler(event, data)

        maintenance = await self.system.get_stat("maintenance_mode", "0")
        if maintenance == "1":
            if isinstance(event, Message):
                await event.reply("Bot is under maintenance. Try again later.")
            elif isinstance(event, CallbackQuery):
                await event.answer("Bot is under maintenance.", show_alert=True)
            return

        if not await self.whitelist.is_whitelisted(user_id):
            if isinstance(event, Message) and event.text and event.text.startswith("/start"):
                await event.reply(
                    f"Welcome! You're not authorized yet.\nContact admin.\n\nYour ID: {user_id}"
                )
            return

        if await self.whitelist.is_suspended(user_id):
            if isinstance(event, Message):
                await event.reply("Your account is suspended. Contact admin.")
            elif isinstance(event, CallbackQuery):
                await event.answer("Account suspended.", show_alert=True)
            return

        if isinstance(event, CallbackQuery) and event.data and event.data != "cancel":
            if not await self.whitelist.check_daily_limit(user_id):
                await event.answer("Daily limit reached. Try tomorrow.", show_alert=True)
                return

        return await handler(event, data)
