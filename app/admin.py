"""
Access control middleware.
Enforces whitelist, suspension, maintenance, rate limits.
"""

from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject

from app.config import BotConfig, logger
from app.database import WhitelistRepo, SystemRepo


class AccessMiddleware(BaseMiddleware):
    def __init__(self, config: BotConfig, whitelist: WhitelistRepo, system: SystemRepo):
        self.config = config
        self.whitelist = whitelist
        self.system = system
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user_id = self._get_user_id(event)
        if user_id is None:
            return

        if user_id == self.config.admin_id:
            return await handler(event, data)

        maintenance = await self.system.get_stat("maintenance_mode", "0")
        if maintenance == "1":
            await self._reply(event, "🔧 Bot is under maintenance. Try again later.")
            return

        if not await self.whitelist.is_whitelisted(user_id):
            if isinstance(event, Message) and event.text and event.text.startswith("/start"):
                await self._reply(
                    event,
                    f"👋 You're not authorized yet.\nContact admin.\n\nYour ID: `{user_id}`",
                )
            return

        if await self.whitelist.is_suspended(user_id):
            await self._reply(event, "🔴 Your account is suspended. Contact admin.")
            return

        if isinstance(event, CallbackQuery) and event.data and event.data != "cancel":
            if not await self.whitelist.check_daily_limit(user_id):
                await self._reply(event, "⚠️ Daily limit reached. Try tomorrow.")
                return

        return await handler(event, data)

    @staticmethod
    def _get_user_id(event: TelegramObject) -> int | None:
        if isinstance(event, Message) and event.from_user:
            return event.from_user.id
        if isinstance(event, CallbackQuery) and event.from_user:
            return event.from_user.id
        return None

    @staticmethod
    async def _reply(event: TelegramObject, text: str) -> None:
        try:
            if isinstance(event, Message):
                await event.reply(text, parse_mode="Markdown")
            elif isinstance(event, CallbackQuery):
                await event.answer(text[:200], show_alert=True)
        except Exception as e:
            logger.warning(f"Middleware reply failed: {e}")
