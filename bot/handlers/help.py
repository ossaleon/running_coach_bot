from telegram import Update
from telegram.ext import ContextTypes

from db import database as db


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await db.get_user(update.effective_user.id)

    if not user or not user.is_authorized:
        await update.message.reply_text(
            "AI Running Coach\n\n"
            "Use /start to authenticate and get started."
        )
        return

    commands = (
        "*Available Commands:*\n\n"
        "/linkstrava - Connect your Strava account\n"
        "/assess - Complete fitness assessment\n"
        "/objective - Set your training goal\n"
        "/plan - View or regenerate weekly plan\n"
        "/feedback - Submit feedback for your last run\n"
        "/settings - Change reminder time or timezone\n"
        "/status - View your profile and current plan\n"
        "/help - Show this message"
    )
    await update.message.reply_text(commands, parse_mode="Markdown")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await db.get_user(update.effective_user.id)
    if not user or not user.is_authorized:
        await update.message.reply_text("Please use /start to authenticate first.")
        return

    lines = [f"*Profile - {user.first_name or 'Runner'}*\n"]

    # Strava
    if user.has_strava:
        lines.append("Strava: Connected")
    else:
        lines.append("Strava: Not linked (/linkstrava)")

    # Assessment
    if user.assessment_done:
        lines.append(f"Experience: {user.experience_level or 'N/A'}")
        lines.append(f"Weekly mileage: {user.weekly_mileage_km or 'N/A'} km")
        if user.max_hr:
            lines.append(f"Max HR: {user.max_hr}")
    else:
        lines.append("Assessment: Not done (/assess)")

    # Objective
    if user.has_objective:
        lines.append(f"\n*Objective:* {user.objective_type} - {user.objective_target}")
        if user.objective_date:
            lines.append(f"Target date: {user.objective_date}")
    else:
        lines.append("\nObjective: Not set (/objective)")

    # Current plan
    plan = await db.get_active_plan(user.telegram_id)
    if plan:
        lines.append(f"\n*Active plan:* Week of {plan.week_start}")
    else:
        lines.append("\nNo active plan (/plan)")

    # Recent activity
    last = await db.get_last_activity(user.telegram_id)
    if last:
        lines.append(
            f"\n*Last run:* {last.distance_km:.1f} km in {last.duration_formatted} "
            f"({last.pace_min_per_km}/km) - {last.start_date}"
        )

    # Settings
    lines.append(f"\n*Settings:*")
    lines.append(f"Reminder: {user.reminder_time}")
    lines.append(f"Timezone: {user.timezone}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
