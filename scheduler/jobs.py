import datetime as dt
import json
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ai.coach import get_coaching_response
from bot.utils import send_markdown
from ai.context import (
    compute_compliance,
    extract_todays_session,
    format_activities,
    format_plan,
)
from ai.prompts import DAILY_REMINDER_PROMPT, WEEKLY_PLAN_PROMPT, WEEKLY_REVIEW_PROMPT
from config import WEEKLY_PLAN_DAY, WEEKLY_PLAN_TIME, WEEKLY_REVIEW_TIME
from db import database as db

logger = logging.getLogger(__name__)


async def schedule_user_jobs(application, telegram_id: int) -> None:
    """Schedule (or reschedule) all recurring jobs for a user."""
    user = await db.get_user(telegram_id)
    if not user or not user.is_authorized:
        return

    job_queue = application.job_queue

    # Remove existing jobs for this user
    for job_name_prefix in ("daily_reminder_", "weekly_plan_", "weekly_review_"):
        name = f"{job_name_prefix}{telegram_id}"
        existing = job_queue.get_jobs_by_name(name)
        for job in existing:
            job.schedule_removal()

    tz = ZoneInfo(user.timezone)
    reminder_h, reminder_m = map(int, user.reminder_time.split(":"))

    # Daily reminder
    job_queue.run_daily(
        daily_reminder_job,
        time=dt.time(hour=reminder_h, minute=reminder_m, tzinfo=tz),
        data={"telegram_id": telegram_id},
        name=f"daily_reminder_{telegram_id}",
    )

    # Weekly plan generation
    plan_h, plan_m = map(int, WEEKLY_PLAN_TIME.split(":"))
    job_queue.run_daily(
        weekly_plan_job,
        time=dt.time(hour=plan_h, minute=plan_m, tzinfo=tz),
        days=(WEEKLY_PLAN_DAY,),
        data={"telegram_id": telegram_id},
        name=f"weekly_plan_{telegram_id}",
    )

    # Weekly review
    review_h, review_m = map(int, WEEKLY_REVIEW_TIME.split(":"))
    job_queue.run_daily(
        weekly_review_job,
        time=dt.time(hour=review_h, minute=review_m, tzinfo=tz),
        days=(WEEKLY_PLAN_DAY,),
        data={"telegram_id": telegram_id},
        name=f"weekly_review_{telegram_id}",
    )

    logger.info(
        f"Scheduled jobs for user {telegram_id}: "
        f"reminder at {user.reminder_time}, "
        f"plan on day {WEEKLY_PLAN_DAY} at {WEEKLY_PLAN_TIME}, "
        f"review on day {WEEKLY_PLAN_DAY} at {WEEKLY_REVIEW_TIME}"
    )


async def daily_reminder_job(context) -> None:
    """Send daily training reminder."""
    telegram_id = context.job.data["telegram_id"]
    try:
        user = await db.get_user(telegram_id)
        if not user or not user.has_objective:
            return

        plan = await db.get_active_plan(telegram_id)
        if not plan:
            return

        todays_session = extract_todays_session(plan)

        if todays_session.get("type", "").lower() == "rest":
            await context.bot.send_message(
                chat_id=telegram_id,
                text="Rest day today! Recovery is training. Stay hydrated and stretch.",
            )
            return

        session_str = json.dumps(todays_session, indent=2)

        last_act = await db.get_last_activity(telegram_id)
        yesterday_str = "No run yesterday."
        if last_act:
            yesterday_str = (
                f"{last_act.name}: {last_act.distance_km:.1f} km, "
                f"{last_act.pace_min_per_km}/km"
            )

        prompt = DAILY_REMINDER_PROMPT.format(
            todays_session=session_str,
            yesterday_summary=yesterday_str,
        )
        response = await get_coaching_response(telegram_id, prompt, "daily_reminder")

        await send_markdown(context.bot, telegram_id, response)
    except Exception:
        logger.exception(f"Error in daily reminder for user {telegram_id}")


async def weekly_plan_job(context) -> None:
    """Generate next week's training plan."""
    telegram_id = context.job.data["telegram_id"]
    try:
        user = await db.get_user(telegram_id)
        if not user or not user.has_objective:
            return

        # Complete current plan
        await db.complete_current_plan(telegram_id)

        # Build prompt
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

        prompt = WEEKLY_PLAN_PROMPT.format(
            last_week_summary=last_week_summary,
            last_week_activities=last_week_activities,
            last_week_feedback=last_week_feedback,
            preferred_days=user.preferred_days or "Any",
        )

        response = await get_coaching_response(telegram_id, prompt, "weekly_plan")

        # Extract JSON and store
        import re
        match = re.search(r"```json\s*(\{.*?\})\s*```", response, re.DOTALL)
        plan_json = match.group(1) if match else "{}"

        monday = datetime.now()
        monday = monday - timedelta(days=monday.weekday()) + timedelta(days=7)
        week_start = monday.strftime("%Y-%m-%d")

        await db.create_weekly_plan(telegram_id, week_start, plan_json, response)

        from bot.utils import strip_json_blocks

        await send_markdown(context.bot, telegram_id, strip_json_blocks(response))
    except Exception:
        logger.exception(f"Error in weekly plan generation for user {telegram_id}")


async def weekly_review_job(context) -> None:
    """Review the current training week."""
    telegram_id = context.job.data["telegram_id"]
    try:
        user = await db.get_user(telegram_id)
        if not user:
            return

        plan = await db.get_active_plan(telegram_id)
        if not plan:
            return

        # Get this week's activities
        week_acts = []
        if plan.week_start:
            week_acts = await db.get_activities_for_week(telegram_id, plan.week_start)

        compliance = compute_compliance(plan, week_acts)
        plan_summary = format_plan(plan)
        activities_summary = format_activities(week_acts)

        prompt = WEEKLY_REVIEW_PROMPT.format(
            plan_summary=plan_summary,
            activities_summary=activities_summary,
            compliance_pct=f"{compliance:.0f}",
        )

        response = await get_coaching_response(telegram_id, prompt, "weekly_review")

        await db.update_plan_review(plan.id, response, compliance)

        await send_markdown(context.bot, telegram_id, response)
    except Exception:
        logger.exception(f"Error in weekly review for user {telegram_id}")
