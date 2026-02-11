import logging

from telegram import Update
from telegram.ext import (
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from bot.conversations import OnboardingState
from config import BOT_PASSWORD
from db import database as db

logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = await db.get_user(update.effective_user.id)
    if user and user.is_authorized:
        await update.message.reply_text(
            f"Welcome back, {update.effective_user.first_name}!\n\n"
            "Use /help to see available commands."
        )
        return ConversationHandler.END

    await db.create_user(
        telegram_id=update.effective_user.id,
        username=update.effective_user.username,
        first_name=update.effective_user.first_name,
    )
    await update.message.reply_text(
        "Welcome to your AI Running Coach!\n\n"
        "Please enter the access password to get started:"
    )
    return OnboardingState.PASSWORD


async def check_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text.strip() == BOT_PASSWORD:
        await db.authorize_user(update.effective_user.id)
        logger.info(f"User {update.effective_user.id} authorized successfully")
        await update.message.reply_text(
            "Access granted! Welcome aboard.\n\n"
            "Here's how to get started:\n"
            "1. /linkstrava - Connect your Strava account\n"
            "2. /assess - Complete your fitness assessment\n"
            "3. /objective - Set your training goal\n"
            "4. /plan - Get your first weekly plan\n\n"
            "Use /help anytime to see all commands."
        )
        # Schedule jobs for this user
        from scheduler.jobs import schedule_user_jobs
        await schedule_user_jobs(context.application, update.effective_user.id)
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            "Incorrect password. Please try again:"
        )
        return OnboardingState.PASSWORD


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Setup cancelled. Use /start to try again.")
    return ConversationHandler.END


def get_onboarding_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("start", start_command)],
        states={
            OnboardingState.PASSWORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, check_password),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="onboarding",
        persistent=False,
    )
