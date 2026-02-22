import logging

from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from ai.coach import get_coaching_response
from ai.context import format_user_profile
from ai.prompts import OBJECTIVE_PROMPT
from bot.conversations import ObjectiveState
from bot.keyboards import confirm_keyboard, objective_type_keyboard
from db import database as db

logger = logging.getLogger(__name__)


async def objective_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = await db.get_user(update.effective_user.id)
    if not user or not user.is_authorized:
        await update.message.reply_text("Please use /start to authenticate first.")
        return ConversationHandler.END
    if not user.assessment_done:
        await update.message.reply_text(
            "Please complete your fitness assessment first with /assess."
        )
        return ConversationHandler.END

    context.user_data["objective"] = {}
    await update.message.reply_text(
        "Let's set your training goal.\n\n"
        "What are you training for?",
        reply_markup=objective_type_keyboard(),
    )
    return ObjectiveState.TYPE


async def type_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    obj_type = query.data.replace("obj_", "")
    context.user_data["objective"]["type"] = obj_type

    if obj_type in ("base_building", "general_fitness"):
        context.user_data["objective"]["target"] = obj_type
        await query.edit_message_text(
            f"Goal: {obj_type.replace('_', ' ').title()}\n\n"
            "By when would you like to achieve this? (YYYY-MM-DD)\n"
            "Or type 'ongoing' for no specific date."
        )
        return ObjectiveState.DATE

    await query.edit_message_text(
        f"Goal: {obj_type}\n\n"
        "What's your target? (e.g., 'sub-25', 'finish', 'under 1:50')"
    )
    return ObjectiveState.TARGET


async def target_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["objective"]["target"] = update.message.text.strip()
    await update.message.reply_text(
        "When is your target date? (YYYY-MM-DD)\n"
        "Or type 'ongoing' for no specific date."
    )
    return ObjectiveState.DATE


async def date_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text.lower() != "ongoing":
        # Basic date validation
        try:
            from datetime import datetime
            datetime.strptime(text, "%Y-%m-%d")
        except ValueError:
            await update.message.reply_text(
                "Please use YYYY-MM-DD format (e.g., 2026-06-15) or 'ongoing':"
            )
            return ObjectiveState.DATE

    context.user_data["objective"]["date"] = text
    data = context.user_data["objective"]

    summary = (
        "*Training Objective:*\n\n"
        f"Goal: {data['type']}\n"
        f"Target: {data['target']}\n"
        f"Date: {data['date']}\n\n"
        "Does this look correct?"
    )
    from bot.utils import reply_markdown

    await reply_markdown(update.message, summary, reply_markup=confirm_keyboard())
    return ObjectiveState.CONFIRM


async def confirm_objective(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "confirm_no":
        context.user_data["objective"] = {}
        await query.edit_message_text(
            "Let's start over. What are you training for?",
            reply_markup=objective_type_keyboard(),
        )
        return ObjectiveState.TYPE

    data = context.user_data["objective"]
    telegram_id = update.effective_user.id

    await db.update_user_objective(
        telegram_id,
        objective_type=data["type"],
        objective_target=data["target"],
        objective_date=data["date"],
    )

    await query.edit_message_text("Objective saved! Analyzing your goal...")

    # Get AI analysis
    user = await db.get_user(telegram_id)
    obj_str = f"Type: {data['type']}\nTarget: {data['target']}\nDate: {data['date']}"
    profile_str = format_user_profile(user)
    prompt = OBJECTIVE_PROMPT.format(
        objective_data=obj_str, profile_summary=profile_str
    )
    response = await get_coaching_response(telegram_id, prompt, "objective")

    from bot.utils import send_markdown

    await send_markdown(context.bot, telegram_id, response)
    await context.bot.send_message(
        chat_id=telegram_id,
        text="Use /plan to generate your first weekly training plan!",
    )

    context.user_data.pop("objective", None)
    return ConversationHandler.END


async def cancel_objective(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("objective", None)
    await update.message.reply_text("Objective setup cancelled. Use /objective to try again.")
    return ConversationHandler.END


def get_objective_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("objective", objective_start)],
        states={
            ObjectiveState.TYPE: [
                CallbackQueryHandler(type_received, pattern=r"^obj_"),
            ],
            ObjectiveState.TARGET: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, target_received),
            ],
            ObjectiveState.DATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, date_received),
            ],
            ObjectiveState.CONFIRM: [
                CallbackQueryHandler(confirm_objective, pattern=r"^confirm_"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_objective)],
        name="objective",
        persistent=False,
    )
