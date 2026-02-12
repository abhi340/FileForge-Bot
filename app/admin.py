import os
from datetime import datetime

from aiogram import Router, Bot
from aiogram.types import Message
from aiogram.filters import Command

from app.config import BotConfig, logger
from app.database import WhitelistRepo, UsageRepo, SystemRepo

router = Router(name="admin")


class AdminService:
    def __init__(self, whitelist, usage, system):
        self.whitelist = whitelist
        self.usage = usage
        self.system = system

    async def record_start(self):
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        await self.system.set_stat("bot_start_time", now)

    async def is_maintenance(self):
        return await self.system.get_stat("maintenance_mode", "0") == "1"

    async def global_stats(self):
        total = await self.usage.total_processed()
        today = await self.usage.today_processed()
        sf = await self.usage.success_failure()
        dist = await self.usage.file_type_dist()
        top = await self.usage.top_users(5)
        avg = await self.usage.avg_time()
        errors = await self.usage.error_count()
        active = await self.usage.active_today()
        started = await self.system.get_stat("bot_start_time", "N/A")
        total_ops = sf["success"] + sf["failure"]
        rate = round((sf["success"] / total_ops) * 100, 1) if total_ops > 0 else 0
        dist_str = "\n".join([f"  {d['file_type']}: {d['c']}" for d in dist[:5]]) or "  No data"
        top_str = "\n".join([f"  {t['user_id']}: {t['c']} ops" for t in top]) or "  No data"
        return (
            f"Global Statistics\n"
            f"Total: {total}\n"
            f"Today: {today}\n"
            f"Success: {sf['success']} | Fail: {sf['failure']}\n"
            f"Rate: {rate}%\n"
            f"Avg time: {avg}ms\n"
            f"Errors: {errors}\n"
            f"Active today: {active}\n"
            f"Started: {started}\n\n"
            f"File Types:\n{dist_str}\n\n"
            f"Top Users:\n{top_str}"
        )

    async def user_stats(self, user_id):
        user = await self.whitelist.get_user(user_id)
        if not user:
            return f"User {user_id} not found."
        total = await self.usage.user_total(user_id)
        daily = await self.usage.user_today(user_id)
        fail = await self.usage.user_fail_rate(user_id)
        fav = await self.usage.user_fav_type(user_id)
        status = "Active" if user["is_active"] and not user["is_suspended"] else "Suspended"
        return (
            f"User {user_id}\n"
            f"Status: {status}\n"
            f"Total: {total}\n"
            f"Today: {daily} / {user['daily_limit']}\n"
            f"Fail rate: {fail}%\n"
            f"Favorite: {fav}\n"
            f"Joined: {user['created_at']}"
        )

    async def system_health(self):
        maintenance = await self.is_maintenance()
        users = await self.whitelist.list_users()
        total = await self.usage.total_processed()
        errors = await self.usage.error_count()
        return (
            f"System Health\n"
            f"Maintenance: {'ON' if maintenance else 'OFF'}\n"
            f"Users: {len(users)}\n"
            f"Total ops: {total}\n"
            f"Errors: {errors}\n"
            f"PID: {os.getpid()}"
        )


def _is_admin(message, config):
    return message.from_user is not None and message.from_user.id == config.admin_id


def register_admin_handlers(rt, config, service, bot):

    @rt.message(Command("add_user"))
    async def cmd_add_user(message: Message):
        if not _is_admin(message, config):
            return
        args = message.text.split()
        if len(args) != 2 or not args[1].isdigit():
            await message.reply("Usage: /add_user <id>")
            return
        ok = await service.whitelist.add_user(int(args[1]))
        text = f"User {args[1]} added." if ok else f"User {args[1]} already exists."
        await message.reply(text)

    @rt.message(Command("remove_user"))
    async def cmd_remove_user(message: Message):
        if not _is_admin(message, config):
            return
        args = message.text.split()
        if len(args) != 2 or not args[1].isdigit():
            await message.reply("Usage: /remove_user <id>")
            return
        ok = await service.whitelist.remove_user(int(args[1]))
        text = f"User {args[1]} removed." if ok else f"User {args[1]} not found."
        await message.reply(text)

    @rt.message(Command("list_users"))
    async def cmd_list_users(message: Message):
        if not _is_admin(message, config):
            return
        users = await service.whitelist.list_users()
        if not users:
            await message.reply("Whitelist is empty.")
            return
        lines = ["Whitelisted Users:\n"]
        for u in users:
            s = "Active" if u["is_active"] and not u["is_suspended"] else "Suspended"
            lines.append(f"{u['user_id']} - {u['daily_limit']}/day - {s}")
        await message.reply("\n".join(lines))

    @rt.message(Command("suspend_user"))
    async def cmd_suspend(message: Message):
        if not _is_admin(message, config):
            return
        args = message.text.split()
        if len(args) != 2 or not args[1].isdigit():
            await message.reply("Usage: /suspend_user <id>")
            return
        ok = await service.whitelist.suspend_user(int(args[1]))
        text = f"User {args[1]} suspended." if ok else "Not found."
        await message.reply(text)

    @rt.message(Command("unsuspend_user"))
    async def cmd_unsuspend(message: Message):
        if not _is_admin(message, config):
            return
        args = message.text.split()
        if len(args) != 2 or not args[1].isdigit():
            await message.reply("Usage: /unsuspend_user <id>")
            return
        ok = await service.whitelist.unsuspend_user(int(args[1]))
        text = f"User {args[1]} unsuspended." if ok else "Not found."
        await message.reply(text)

    @rt.message(Command("set_limit"))
    async def cmd_set_limit(message: Message):
        if not _is_admin(message, config):
            return
        args = message.text.split()
        if len(args) != 3 or not args[1].isdigit() or not args[2].isdigit():
            await message.reply("Usage: /set_limit <id> <limit>")
            return
        limit = int(args[2])
        if limit < 1:
            await message.reply("Limit must be >= 1.")
            return
        ok = await service.whitelist.set_daily_limit(int(args[1]), limit)
        text = f"Limit for {args[1]} set to {limit}/day" if ok else "Not found."
        await message.reply(text)

    @rt.message(Command("stats"))
    async def cmd_stats(message: Message):
        if not _is_admin(message, config):
            return
        text = await service.global_stats()
        await message.reply(text)

    @rt.message(Command("user_stats"))
    async def cmd_user_stats(message: Message):
        if not _is_admin(message, config):
            return
        args = message.text.split()
        if len(args) != 2 or not args[1].isdigit():
            await message.reply("Usage: /user_stats <id>")
            return
        text = await service.user_stats(int(args[1]))
        await message.reply(text)

    @rt.message(Command("broadcast"))
    async def cmd_broadcast(message: Message):
        if not _is_admin(message, config):
            return
        text = message.text.replace("/broadcast", "", 1).strip()
        if not text:
            await message.reply("Usage: /broadcast <message>")
            return
        user_ids = await service.whitelist.get_active_user_ids()
        ok_count = 0
        fail_count = 0
        for uid in user_ids:
            try:
                await bot.send_message(uid, f"Broadcast:\n\n{text}")
                ok_count += 1
            except Exception as e:
                logger.warning(f"Broadcast failed for {uid}: {e}")
                fail_count += 1
        await message.reply(f"Broadcast sent. Delivered: {ok_count} Failed: {fail_count}")

    @rt.message(Command("maintenance_on"))
    async def cmd_maint_on(message: Message):
        if not _is_admin(message, config):
            return
        await service.system.set_stat("maintenance_mode", "1")
        await message.reply("Maintenance mode ON")

    @rt.message(Command("maintenance_off"))
    async def cmd_maint_off(message: Message):
        if not _is_admin(message, config):
            return
        await service.system.set_stat("maintenance_mode", "0")
        await message.reply("Maintenance mode OFF")

    @rt.message(Command("system_health"))
    async def cmd_health(message: Message):
        if not _is_admin(message, config):
            return
        text = await service.system_health()
        await message.reply(text)
