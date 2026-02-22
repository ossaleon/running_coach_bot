import json
import logging
import re
from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import ContextTypes

from ai.coach import get_coaching_response
from ai.context import (
    compute_compliance,
    format_activities,
    format_plan,
)
from ai.prompts import WEEKLY_PLAN_PROMPT
from db import database as db

logger = logging.getLogger(__name__)


def _next_monday() -> str:
    today = datetime.now()
    days_ahead = 7 - today.weekday()  # Monday is 0
    if days_ahead == 7:
        days_ahead = 0
    next_mon = today + timedelta(days=days_ahead)
    return next_mon.strftime("%Y-%m-%d")


def _this_monday() -> str:
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    return monday.strftime("%Y-%m-%d")


def _extract_json_from_response(text: str) -> str:
    """Extract JSON block from AI response."""
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return match.group(1)
    match = re.search(r"```\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return match.group(1)
    return "{}"


async def plan_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await db.get_user(update.effective_user.id)
    if not user or not user.is_authorized:
        await update.message.reply_text("Please use /start to authenticate first.")
        return
    if not user.has_objective:
        await update.message.reply_text(
            "Please set your training objective first with /objective."
        )
        return

    # Check for existing plan
    current_plan = await db.get_active_plan(user.telegram_id)
    if current_plan:
        from bot.utils import reply_markdown, strip_json_blocks

        await reply_markdown(
            update.message,
            f"*Current plan (week of {current_plan.week_start}):*\n\n"
            f"{strip_json_blocks(current_plan.plan_text)}\n\n"
            "Send /newplan to generate a fresh plan for next week.",
        )
        return

    await _generate_plan(update.effective_user.id, context)


async def newplan_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await db.get_user(update.effective_user.id)
    if not user or not user.is_authorized:
        await update.message.reply_text("Please use /start to authenticate first.")
        return
    if not user.has_objective:
        await update.message.reply_text(
            "Please set your training objective first with /objective."
        )
        return

    await update.message.reply_text("Generating your weekly plan...")
    await _generate_plan(update.effective_user.id, context)


async def _generate_plan(telegram_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate a new weekly plan."""
    user = await db.get_user(telegram_id)

    # Complete current plan if exists
    await db.complete_current_plan(telegram_id)

    # Build plan prompt with context
    last_plan = await db.get_last_completed_plan(telegram_id)
    last_week_summary = "No previous plan." if not last_plan else format_plan(last_plan)

    last_week_activities = "No activities."
    last_week_feedback = "No feedback."
    if last_plan and last_plan.week_start:
        acts = await db.get_activities_for_week(telegram_id, last_plan.week_start)
        if acts:
            compliance = compute_compliance(last_plan, acts)
            last_week_activities = format_activities(acts)
            feedback_parts = []
            for a in acts:
                if a.user_rpe or a.user_feedback:
                    fb = f"- {a.name}: RPE {a.user_rpe or '?'}/10"
                    if a.user_feedback:
                        fb += f" - {a.user_feedback}"
                    feedback_parts.append(fb)
            if feedback_parts:
                last_week_feedback = "\n".join(feedback_parts)

    preferred_days = user.preferred_days or "Any"
    prompt = WEEKLY_PLAN_PROMPT.format(
        last_week_summary=last_week_summary,
        last_week_activities=last_week_activities,
        last_week_feedback=last_week_feedback,
        preferred_days=preferred_days,
    )

    response = await get_coaching_response(telegram_id, prompt, "weekly_plan")

    # Extract JSON and store
    plan_json = _extract_json_from_response(response)
    week_start = _this_monday()

    await db.create_weekly_plan(telegram_id, week_start, plan_json, response)

    from bot.utils import send_markdown, strip_json_blocks

    await send_markdown(context.bot, telegram_id, strip_json_blocks(response))
