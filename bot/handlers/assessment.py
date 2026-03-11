import json
import logging
from datetime import datetime

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
from strava.oauth import get_valid_token
from strava.client import get_recent_activities

logger = logging.getLogger(__name__)


def _format_strava_activities(activities: list[dict]) -> str:
    """Format raw Strava activities into a readable summary for Gemini."""
    if not activities:
        return "No recent running activities found on Strava."

    lines = []
    max_hr_seen = 0
    weeks = {}

    for act in activities:
        distance_km = act.get("distance", 0) / 1000
        moving_time = act.get("moving_time", 0)

        pace_s = moving_time / distance_km if distance_km > 0 else 0
        pace_min = int(pace_s // 60)
        pace_sec = int(pace_s % 60)

        avg_hr = act.get("average_heartrate")
        max_hr = act.get("max_heartrate")
        if max_hr and max_hr > max_hr_seen:
            max_hr_seen = max_hr

        date = act.get("start_date_local", "")[:10]

        try:
            dt = datetime.fromisoformat(date)
            week_key = dt.strftime("%Y-W%W")
            weeks[week_key] = weeks.get(week_key, 0) + distance_km
        except ValueError:
            pass

        line = f"- {date}: {distance_km:.1f} km, {pace_min}:{pace_sec:02d}/km"
        if avg_hr:
            line += f", avg HR {avg_hr:.0f}"
        if max_hr:
            line += f", max HR {max_hr:.0f}"
        line += f" ({act.get('name', 'Run')})"
        lines.append(line)

    run_count = len(lines)
    avg_weekly_km = sum(weeks.values()) / len(weeks) if weeks else 0
    avg_runs_per_week = run_count / len(weeks) if weeks else 0

    summary = [
        f"Total runs analyzed: {run_count}",
        f"Average weekly distance: {avg_weekly_km:.1f} km",
        f"Average runs per week: {avg_runs_per_week:.1f}",
    ]
    if max_hr_seen:
        summary.append(f"Highest HR recorded: {max_hr_seen:.0f}")
    summary.append("")
    summary.append("Individual runs (most recent first):")

    return "\n".join(summary + lines)


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
        "Let's assess your current fitness level.\n"
        "I'll ask a few quick questions, then pull your recent runs "
        "from Strava to get the full picture.\n\n"
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
        "Any injury history I should know about?\n"
        "(e.g., 'knee issues in 2024' or 'none')"
    )
    return AssessmentState.INJURY


async def injury_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["assessment"]["injury_history"] = update.message.text.strip()
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
        f"Injury history: {data.get('injury_history', 'N/A')}\n"
        f"Preferred days: {', '.join(data.get('preferred_days', []))}\n\n"
        "I'll also pull your last 20 runs from Strava.\n"
        "Does this look correct?"
    )
    from bot.utils import edit_markdown

    await edit_markdown(query, summary, reply_markup=confirm_keyboard())
    return AssessmentState.CONFIRM


async def confirm_assessment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "confirm_no":
        context.user_data["assessment"] = {}
        await query.edit_message_text("Let's start over. How old are you?")
        return AssessmentState.AGE

    data = context.user_data["assessment"]
    telegram_id = update.effective_user.id

    await query.edit_message_text(
        "Fetching your Strava data and generating analysis..."
    )

    # Fetch last 20 runs from Strava
    user = await db.get_user(telegram_id)
    strava_data_str = "Could not fetch Strava data."
    try:
        token = await get_valid_token(user)
        raw_activities = await get_recent_activities(token, per_page=30)
        runs = [
            a for a in raw_activities
            if a.get("type") in ("Run", "TrailRun", "VirtualRun")
        ][:20]
        strava_data_str = _format_strava_activities(runs)

        # Derive weekly mileage and max HR from Strava for the DB profile
        if runs:
            weeks = {}
            max_hr_seen = 0
            for act in runs:
                date = act.get("start_date_local", "")[:10]
                try:
                    dt = datetime.fromisoformat(date)
                    week_key = dt.strftime("%Y-W%W")
                    weeks[week_key] = weeks.get(week_key, 0) + act.get("distance", 0) / 1000
                except ValueError:
                    pass
                hr = act.get("max_heartrate")
                if hr and hr > max_hr_seen:
                    max_hr_seen = hr

            avg_weekly = sum(weeks.values()) / len(weeks) if weeks else None
            if avg_weekly:
                data["weekly_mileage_km"] = round(avg_weekly, 1)
            if max_hr_seen:
                data["max_hr"] = int(max_hr_seen)

    except Exception:
        logger.exception("Failed to fetch Strava activities for assessment")

    # Save to database
    await db.update_user_profile(
        telegram_id,
        age=data.get("age"),
        gender=data.get("gender"),
        weekly_mileage_km=data.get("weekly_mileage_km"),
        injury_history=data.get("injury_history"),
        experience_level=data.get("experience_level"),
        preferred_days=json.dumps(data.get("preferred_days", [])),
        max_hr=data.get("max_hr"),
        assessment_done=True,
    )

    # Send both self-reported answers and Strava data to Gemini
    assessment_str = (
        f"Age: {data.get('age')}\n"
        f"Gender: {data.get('gender')}\n"
        f"Experience level: {data.get('experience_level')}\n"
        f"Injury history: {data.get('injury_history')}\n"
        f"Preferred training days: {', '.join(data.get('preferred_days', []))}"
    )

    prompt = ASSESSMENT_PROMPT.format(
        assessment_data=assessment_str,
        strava_data=strava_data_str,
    )
    response = await get_coaching_response(telegram_id, prompt, "assessment")

    # Store the AI assessment so it's available for future plan generation
    await db.update_user_profile(telegram_id, assessment_summary=response)

    from bot.utils import send_markdown

    await send_markdown(context.bot, telegram_id, response)
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
            AssessmentState.INJURY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, injury_received),
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
