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

from bot.conversations import FeedbackState
from bot.keyboards import rpe_keyboard
from db import database as db

logger = logging.getLogger(__name__)


async def feedback_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start manual feedback for the last run."""
    user = await db.get_user(update.effective_user.id)
    if not user or not user.is_authorized:
        await update.message.reply_text("Please use /start to authenticate first.")
        return ConversationHandler.END

    last_activity = await db.get_last_activity(update.effective_user.id)
    if not last_activity:
        await update.message.reply_text("No recent runs found. Complete a run first!")
        return ConversationHandler.END

    context.user_data["feedback_activity_id"] = last_activity.strava_activity_id
    from bot.utils import reply_markdown

    await reply_markdown(
        update.message,
        f"Feedback for: *{last_activity.name or 'Run'}* "
        f"({last_activity.distance_km:.1f} km, {last_activity.pace_min_per_km}/km)\n\n"
        "Rate your perceived effort (1-10):",
        reply_markup=rpe_keyboard(),
    )
    return FeedbackState.RPE


async def rpe_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    rpe = int(query.data.replace("rpe_", ""))
    context.user_data["feedback_rpe"] = rpe
    await query.edit_message_text(
        f"RPE: {rpe}/10\n\n"
        "Any additional comments? (how you felt, pain, energy level, etc.)\n"
        "Type 'skip' to finish."
    )
    return FeedbackState.COMMENTS


async def comments_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    comments = None if text.lower() == "skip" else text

    activity_id = context.user_data.get("feedback_activity_id")
    rpe = context.user_data.get("feedback_rpe")

    if activity_id:
        await db.update_activity_feedback(
            strava_activity_id=activity_id,
            user_rpe=rpe,
            user_feedback=comments,
        )

    await update.message.reply_text(
        "Feedback recorded! This will help me fine-tune your next plan."
    )

    context.user_data.pop("feedback_activity_id", None)
    context.user_data.pop("feedback_rpe", None)
    return ConversationHandler.END


async def cancel_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("feedback_activity_id", None)
    context.user_data.pop("feedback_rpe", None)
    await update.message.reply_text("Feedback cancelled.")
    return ConversationHandler.END


def get_feedback_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("feedback", feedback_start)],
        states={
            FeedbackState.RPE: [
                CallbackQueryHandler(rpe_received, pattern=r"^rpe_"),
            ],
            FeedbackState.COMMENTS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, comments_received),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_feedback)],
        name="feedback",
        persistent=False,
    )


# Standalone RPE callback handler for webhook-triggered RPE prompts
async def rpe_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle RPE button presses from webhook-initiated feedback prompts."""
    query = update.callback_query
    if not query.data.startswith("rpe_"):
        return

    await query.answer()
    rpe = int(query.data.replace("rpe_", ""))

    # Get last activity for this user
    last_activity = await db.get_last_activity(update.effective_user.id)
    if last_activity:
        await db.update_activity_feedback(
            strava_activity_id=last_activity.strava_activity_id,
            user_rpe=rpe,
        )

    await query.edit_message_text(
        f"RPE: {rpe}/10 recorded.\n\n"
        "Any additional comments about this run? Just type them below, "
        "or ignore this to skip."
    )

    # Store in user_data so the general message handler can pick up comments
    context.user_data["pending_run_comments"] = last_activity.strava_activity_id if last_activity else None
