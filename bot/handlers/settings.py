import logging
import re

from telegram import Update
from telegram.ext import ContextTypes

from bot.keyboards import settings_keyboard
from db import database as db

logger = logging.getLogger(__name__)

# Track pending settings changes
_pending_settings: dict[int, str] = {}


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await db.get_user(update.effective_user.id)
    if not user or not user.is_authorized:
        await update.message.reply_text("Please use /start to authenticate first.")
        return

    await update.message.reply_text(
        f"*Current Settings:*\n\n"
        f"Reminder time: {user.reminder_time}\n"
        f"Timezone: {user.timezone}\n\n"
        "What would you like to change?",
        parse_mode="Markdown",
        reply_markup=settings_keyboard(),
    )


async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if query.data == "settings_reminder":
        _pending_settings[update.effective_user.id] = "reminder_time"
        await query.edit_message_text(
            "Enter your new daily reminder time (HH:MM format, 24h).\n"
            "Example: 07:00 or 18:30"
        )
    elif query.data == "settings_timezone":
        _pending_settings[update.effective_user.id] = "timezone"
        await query.edit_message_text(
            "Enter your timezone.\n"
            "Examples: Europe/Rome, America/New_York, Asia/Tokyo\n\n"
            "See: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones"
        )


async def handle_settings_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Handle text input for pending settings changes. Returns True if handled."""
    telegram_id = update.effective_user.id
    pending = _pending_settings.get(telegram_id)
    if not pending:
        return False

    text = update.message.text.strip()

    if pending == "reminder_time":
        if not re.match(r"^\d{2}:\d{2}$", text):
            await update.message.reply_text("Please use HH:MM format (e.g., 07:00):")
            return True
        hours, minutes = map(int, text.split(":"))
        if hours > 23 or minutes > 59:
            await update.message.reply_text("Invalid time. Please use HH:MM format:")
            return True
        await db.update_user_profile(telegram_id, reminder_time=text)
        del _pending_settings[telegram_id]

        # Reschedule reminder
        from scheduler.jobs import schedule_user_jobs
        await schedule_user_jobs(context.application, telegram_id)

        await update.message.reply_text(f"Reminder time updated to {text}.")
        return True

    elif pending == "timezone":
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        try:
            ZoneInfo(text)
        except (ZoneInfoNotFoundError, KeyError):
            await update.message.reply_text(
                "Invalid timezone. Please enter a valid timezone (e.g., Europe/Rome):"
            )
            return True
        await db.update_user_profile(telegram_id, timezone=text)
        del _pending_settings[telegram_id]

        # Reschedule jobs with new timezone
        from scheduler.jobs import schedule_user_jobs
        await schedule_user_jobs(context.application, telegram_id)

        await update.message.reply_text(f"Timezone updated to {text}.")
        return True

    return False
