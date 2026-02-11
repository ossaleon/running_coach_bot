import json
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
from ai.prompts import ASSESSMENT_PROMPT
from bot.conversations import AssessmentState
from bot.keyboards import (
    confirm_keyboard,
    experience_keyboard,
    gender_keyboard,
    preferred_days_keyboard,
)
from db import database as db

logger = logging.getLogger(__name__)


async def assess_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = await db.get_user(update.effective_user.id)
    if not user or not user.is_authorized:
        await update.message.reply_text("Please use /start to authenticate first.")
        return ConversationHandler.END
    if not user.has_strava:
        await update.message.reply_text(
            "Please link your Strava account first with /linkstrava."
        )
        return ConversationHandler.END

    context.user_data["assessment"] = {}
    await update.message.reply_text(
        "Let's assess your current fitness level.\n\n"
        "How old are you?"
    )
    return AssessmentState.AGE


async def age_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        age = int(update.message.text.strip())
        if age < 10 or age > 100:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Please enter a valid age (10-100):")
        return AssessmentState.AGE

    context.user_data["assessment"]["age"] = age
    await update.message.reply_text(
        "What's your gender?",
        reply_markup=gender_keyboard(),
    )
    return AssessmentState.GENDER


async def gender_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    gender = query.data.replace("gender_", "")
    context.user_data["assessment"]["gender"] = gender
    await query.edit_message_text(
        f"Gender: {gender}\n\n"
        "What's your running experience level?",
        reply_markup=experience_keyboard(),
    )
    return AssessmentState.EXPERIENCE


async def experience_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    level = query.data.replace("exp_", "")
    context.user_data["assessment"]["experience_level"] = level
    await query.edit_message_text(
        f"Experience: {level}\n\n"
        "What's your typical weekly mileage in km? (e.g., 30)"
    )
    return AssessmentState.WEEKLY_MILEAGE


async def mileage_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        km = float(update.message.text.strip())
        if km < 0 or km > 300:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Please enter a valid number (0-300 km):")
        return AssessmentState.WEEKLY_MILEAGE

    context.user_data["assessment"]["weekly_mileage_km"] = km
    await update.message.reply_text(
        "What's your most recent race result?\n"
        "(e.g., '5K in 25:00' or '10K in 52:30' or 'none')"
    )
    return AssessmentState.RECENT_RACE


async def race_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["assessment"]["recent_race"] = update.message.text.strip()
    await update.message.reply_text(
        "Any injury history I should know about?\n"
        "(e.g., 'knee issues in 2024' or 'none')"
    )
    return AssessmentState.INJURY


async def injury_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["assessment"]["injury_history"] = update.message.text.strip()
    await update.message.reply_text(
        "What's your maximum heart rate? (if known)\n"
        "Type 'skip' if you don't know."
    )
    return AssessmentState.MAX_HR


async def max_hr_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().lower()
    if text != "skip":
        try:
            hr = int(text)
            if hr < 100 or hr > 250:
                raise ValueError
            context.user_data["assessment"]["max_hr"] = hr
        except ValueError:
            await update.message.reply_text("Please enter a valid HR (100-250) or 'skip':")
            return AssessmentState.MAX_HR

    await update.message.reply_text(
        "What's your resting heart rate? (if known)\n"
        "Type 'skip' if you don't know."
    )
    return AssessmentState.REST_HR


async def rest_hr_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().lower()
    if text != "skip":
        try:
            hr = int(text)
            if hr < 30 or hr > 120:
                raise ValueError
            context.user_data["assessment"]["rest_hr"] = hr
        except ValueError:
            await update.message.reply_text("Please enter a valid resting HR (30-120) or 'skip':")
            return AssessmentState.REST_HR

    context.user_data["assessment"]["preferred_days"] = []
    await update.message.reply_text(
        "Which days do you prefer to train? Tap to select, then press Done.",
        reply_markup=preferred_days_keyboard([]),
    )
    return AssessmentState.PREFERRED_DAYS


async def days_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "days_done":
        selected = context.user_data["assessment"].get("preferred_days", [])
        if not selected:
            await query.answer("Please select at least one day.", show_alert=True)
            return AssessmentState.PREFERRED_DAYS
        return await _show_summary(query, context)

    day = query.data.replace("day_", "")
    selected = context.user_data["assessment"].get("preferred_days", [])
    if day in selected:
        selected.remove(day)
    else:
        selected.append(day)
    context.user_data["assessment"]["preferred_days"] = selected

    await query.edit_message_text(
        "Which days do you prefer to train? Tap to select, then press Done.",
        reply_markup=preferred_days_keyboard(selected),
    )
    return AssessmentState.PREFERRED_DAYS


async def _show_summary(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    data = context.user_data["assessment"]
    summary = (
        "*Assessment Summary:*\n\n"
        f"Age: {data.get('age', 'N/A')}\n"
        f"Gender: {data.get('gender', 'N/A')}\n"
        f"Experience: {data.get('experience_level', 'N/A')}\n"
        f"Weekly mileage: {data.get('weekly_mileage_km', 'N/A')} km\n"
        f"Recent race: {data.get('recent_race', 'N/A')}\n"
        f"Injury history: {data.get('injury_history', 'N/A')}\n"
        f"Max HR: {data.get('max_hr', 'N/A')}\n"
        f"Resting HR: {data.get('rest_hr', 'N/A')}\n"
        f"Preferred days: {', '.join(data.get('preferred_days', []))}\n\n"
        "Does this look correct?"
    )
    await query.edit_message_text(
        summary,
        parse_mode="Markdown",
        reply_markup=confirm_keyboard(),
    )
    return AssessmentState.CONFIRM


async def confirm_assessment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "confirm_no":
        context.user_data["assessment"] = {}
        await query.edit_message_text(
            "Let's start over. How old are you?"
        )
        return AssessmentState.AGE

    # Save to database
    data = context.user_data["assessment"]
    telegram_id = update.effective_user.id

    await db.update_user_profile(
        telegram_id,
        age=data.get("age"),
        gender=data.get("gender"),
        weekly_mileage_km=data.get("weekly_mileage_km"),
        recent_race=data.get("recent_race"),
        injury_history=data.get("injury_history"),
        experience_level=data.get("experience_level"),
        preferred_days=json.dumps(data.get("preferred_days", [])),
        max_hr=data.get("max_hr"),
        rest_hr=data.get("rest_hr"),
        assessment_done=True,
    )

    await query.edit_message_text("Assessment saved! Generating your initial analysis...")

    # Get AI analysis
    assessment_str = "\n".join(f"{k}: {v}" for k, v in data.items())
    prompt = ASSESSMENT_PROMPT.format(assessment_data=assessment_str)
    response = await get_coaching_response(telegram_id, prompt, "assessment")

    await context.bot.send_message(
        chat_id=telegram_id,
        text=response,
        parse_mode="Markdown",
    )
    await context.bot.send_message(
        chat_id=telegram_id,
        text="Next step: /objective to set your training goal!",
    )

    context.user_data.pop("assessment", None)
    return ConversationHandler.END


async def cancel_assessment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("assessment", None)
    await update.message.reply_text("Assessment cancelled. Use /assess to try again.")
    return ConversationHandler.END


def get_assessment_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("assess", assess_start)],
        states={
            AssessmentState.AGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, age_received),
            ],
            AssessmentState.GENDER: [
                CallbackQueryHandler(gender_received, pattern=r"^gender_"),
            ],
            AssessmentState.EXPERIENCE: [
                CallbackQueryHandler(experience_received, pattern=r"^exp_"),
            ],
            AssessmentState.WEEKLY_MILEAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, mileage_received),
            ],
            AssessmentState.RECENT_RACE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, race_received),
            ],
            AssessmentState.INJURY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, injury_received),
            ],
            AssessmentState.MAX_HR: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, max_hr_received),
            ],
            AssessmentState.REST_HR: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, rest_hr_received),
            ],
            AssessmentState.PREFERRED_DAYS: [
                CallbackQueryHandler(days_toggle, pattern=r"^day_|^days_done$"),
            ],
            AssessmentState.CONFIRM: [
                CallbackQueryHandler(confirm_assessment, pattern=r"^confirm_"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_assessment)],
        name="assessment",
        persistent=False,
    )
