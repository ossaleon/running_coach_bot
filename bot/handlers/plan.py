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
from ai.prompts import PLAN_REVISION_PROMPT, WEEKLY_PLAN_PROMPT
from bot.keyboards import plan_approval_keyboard
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


def _store_pending_plan(context: ContextTypes.DEFAULT_TYPE, telegram_id: int, response: str) -> None:
    """Store a generated plan as pending approval in bot_data."""
    plan_json = _extract_json_from_response(response)
    week_start = _this_monday()
    context.bot_data[f"pending_plan_{telegram_id}"] = {
        "response": response,
        "plan_json": plan_json,
        "week_start": week_start,
    }
    # Clear any feedback-pending flag
    context.bot_data.pop(f"plan_feedback_pending_{telegram_id}", None)


async def _send_plan_for_approval(bot, telegram_id: int, response: str) -> None:
    """Send plan text with approval buttons."""
    from bot.utils import send_markdown, strip_json_blocks

    clean_text = strip_json_blocks(response)
    # Split if too long for Telegram (4096 char limit)
    if len(clean_text) > 3800:
        await send_markdown(bot, telegram_id, clean_text)
        await bot.send_message(
            chat_id=telegram_id,
            text="Approve this plan or reject it with feedback:",
            reply_markup=plan_approval_keyboard(),
        )
    else:
        await send_markdown(
            bot, telegram_id, clean_text,
            reply_markup=plan_approval_keyboard(),
        )


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
    """Generate a new weekly plan and send for approval."""
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

    # Store as pending (not in DB yet) and send for approval
    _store_pending_plan(context, telegram_id, response)
    await _send_plan_for_approval(context.bot, telegram_id, response)


async def plan_approval_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle plan approval or rejection."""
    query = update.callback_query
    await query.answer()
    telegram_id = update.effective_user.id
    action = query.data  # "plan_approve" or "plan_reject"

    pending_key = f"pending_plan_{telegram_id}"
    pending = context.bot_data.get(pending_key)

    if not pending:
        await query.edit_message_text("No pending plan to review. Use /newplan to generate one.")
        return

    if action == "plan_approve":
        # Save to DB
        await db.create_weekly_plan(
            telegram_id,
            pending["week_start"],
            pending["plan_json"],
            pending["response"],
        )
        context.bot_data.pop(pending_key, None)
        context.bot_data.pop(f"plan_feedback_pending_{telegram_id}", None)
        await query.edit_message_reply_markup(reply_markup=None)
        await context.bot.send_message(
            chat_id=telegram_id,
            text="Plan approved! Your training week is set. Good luck!",
        )

    elif action == "plan_reject":
        # Ask for feedback
        context.bot_data[f"plan_feedback_pending_{telegram_id}"] = True
        await query.edit_message_reply_markup(reply_markup=None)
        await context.bot.send_message(
            chat_id=telegram_id,
            text="What would you like changed? Send me your feedback and I'll revise the plan.",
        )


async def plan_feedback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text feedback after plan rejection. Regenerate plan with feedback."""
    telegram_id = update.effective_user.id
    feedback_key = f"plan_feedback_pending_{telegram_id}"
    pending_key = f"pending_plan_{telegram_id}"

    if not context.bot_data.get(feedback_key):
        return  # Not waiting for plan feedback, ignore

    pending = context.bot_data.get(pending_key)
    if not pending:
        context.bot_data.pop(feedback_key, None)
        await update.message.reply_text("No pending plan found. Use /newplan to generate one.")
        return

    feedback = update.message.text.strip()
    context.bot_data.pop(feedback_key, None)

    await update.message.reply_text("Revising your plan based on your feedback...")

    # Generate revised plan
    from bot.utils import strip_json_blocks

    prompt = PLAN_REVISION_PROMPT.format(
        previous_plan=strip_json_blocks(pending["response"]),
        feedback=feedback,
    )
    response = await get_coaching_response(telegram_id, prompt, "weekly_plan")

    # Store revised plan as pending and send for approval
    _store_pending_plan(context, telegram_id, response)
    await _send_plan_for_approval(context.bot, telegram_id, response)
