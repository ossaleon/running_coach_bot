import json
import logging
from datetime import datetime, timedelta

from db import database as db
from db.models import User, Activity, WeeklyPlan

logger = logging.getLogger(__name__)


def format_user_profile(user: User) -> str:
    parts = []
    if user.first_name:
        parts.append(f"Name: {user.first_name}")
    if user.age:
        parts.append(f"Age: {user.age}")
    if user.gender:
        parts.append(f"Gender: {user.gender}")
    if user.experience_level:
        parts.append(f"Experience: {user.experience_level}")
    if user.weekly_mileage_km:
        parts.append(f"Typical weekly mileage: {user.weekly_mileage_km} km")
    if user.recent_race:
        parts.append(f"Recent race: {user.recent_race}")
    if user.max_hr:
        parts.append(f"Max HR: {user.max_hr}")
    if user.rest_hr:
        parts.append(f"Resting HR: {user.rest_hr}")
    if user.injury_history:
        parts.append(f"Injury history: {user.injury_history}")
    if user.preferred_days:
        parts.append(f"Preferred training days: {user.preferred_days}")
    return "\n".join(parts) if parts else "No profile data yet."


def format_objective(user: User) -> str:
    if not user.has_objective:
        return "No objective set."
    parts = [f"Goal: {user.objective_type}"]
    if user.objective_target:
        parts.append(f"Target: {user.objective_target}")
    if user.objective_date:
        parts.append(f"Target date: {user.objective_date}")
    return "\n".join(parts)


def format_activity(activity: Activity) -> str:
    parts = [
        f"- {activity.name or 'Run'}: {activity.distance_km:.1f} km in {activity.duration_formatted}",
        f"  Pace: {activity.pace_min_per_km}/km",
    ]
    if activity.avg_heartrate:
        parts.append(f"  Avg HR: {activity.avg_heartrate:.0f} bpm")
    if activity.max_heartrate:
        parts.append(f"  Max HR: {activity.max_heartrate:.0f} bpm")
    if activity.avg_cadence:
        parts.append(f"  Cadence: {activity.avg_cadence:.0f} spm")
    if activity.total_elevation_m:
        parts.append(f"  Elevation: {activity.total_elevation_m:.0f} m")
    if activity.user_rpe:
        parts.append(f"  RPE: {activity.user_rpe}/10")
    if activity.user_feedback:
        parts.append(f"  User notes: {activity.user_feedback}")
    return "\n".join(parts)


def format_activities(activities: list[Activity]) -> str:
    if not activities:
        return "No recent activities."
    return "\n\n".join(format_activity(a) for a in activities)


def format_plan(plan: WeeklyPlan) -> str:
    if not plan:
        return "No active plan."
    parts = [f"Week of {plan.week_start} (Status: {plan.status})"]
    if plan.plan_text:
        # Truncate if very long
        text = plan.plan_text
        if len(text) > 1500:
            text = text[:1500] + "..."
        parts.append(text)
    return "\n".join(parts)


def extract_todays_session(plan: WeeklyPlan) -> dict:
    """Extract today's session from the plan JSON."""
    if not plan or not plan.plan_json:
        return {"type": "Rest", "notes": "No plan available"}
    try:
        data = json.loads(plan.plan_json)
        sessions = data.get("sessions", [])
        today_name = datetime.now().strftime("%A")
        for session in sessions:
            if session.get("day", "").lower() == today_name.lower():
                return session
        return {"type": "Rest", "notes": "No session planned for today"}
    except (json.JSONDecodeError, KeyError):
        return {"type": "Unknown", "notes": "Could not parse plan"}


def compute_compliance(plan: WeeklyPlan, activities: list[Activity]) -> float:
    """Compute compliance percentage: completed sessions / planned sessions."""
    if not plan or not plan.plan_json:
        return 0.0
    try:
        data = json.loads(plan.plan_json)
        sessions = data.get("sessions", [])
        planned = [s for s in sessions if s.get("type", "").lower() != "rest"]
        if not planned:
            return 100.0
        # Match activities to planned sessions by checking if a run exists on that day
        matched = 0
        for session in planned:
            day_name = session.get("day", "")
            for act in activities:
                if act.start_date:
                    try:
                        act_day = datetime.fromisoformat(act.start_date).strftime("%A")
                        if act_day.lower() == day_name.lower():
                            matched += 1
                            break
                    except ValueError:
                        continue
        return (matched / len(planned)) * 100.0
    except (json.JSONDecodeError, KeyError):
        return 0.0


async def build_context(telegram_id: int, interaction_type: str) -> str:
    """Build context string for AI based on interaction type."""
    user = await db.get_user(telegram_id)
    if not user:
        return "Unknown user."

    profile = format_user_profile(user)
    objective = format_objective(user)
    current_plan = await db.get_active_plan(telegram_id)

    parts = [
        f"## Athlete Profile\n{profile}",
        f"\n## Current Objective\n{objective}",
    ]

    if interaction_type == "run_feedback":
        parts.append(f"\n## Current Plan\n{format_plan(current_plan)}")
        recent = await db.get_recent_activities(telegram_id, limit=5)
        if recent:
            parts.append(f"\n## Recent Activities\n{format_activities(recent)}")
        todays = extract_todays_session(current_plan) if current_plan else None
        if todays:
            parts.append(f"\n## Today's Planned Session\n{json.dumps(todays, indent=2)}")

    elif interaction_type == "weekly_plan":
        last_plan = await db.get_last_completed_plan(telegram_id)
        if last_plan:
            parts.append(f"\n## Last Week's Plan\n{format_plan(last_plan)}")
            if last_plan.week_start:
                week_acts = await db.get_activities_for_week(telegram_id, last_plan.week_start)
                compliance = compute_compliance(last_plan, week_acts)
                parts.append(f"\n## Last Week's Activities (Compliance: {compliance:.0f}%)\n{format_activities(week_acts)}")
        elif current_plan:
            parts.append(f"\n## Current Plan\n{format_plan(current_plan)}")
        recent = await db.get_recent_activities(telegram_id, limit=10)
        if recent:
            parts.append(f"\n## Recent Activities\n{format_activities(recent)}")

    elif interaction_type == "weekly_review":
        parts.append(f"\n## This Week's Plan\n{format_plan(current_plan)}")
        if current_plan and current_plan.week_start:
            week_acts = await db.get_activities_for_week(telegram_id, current_plan.week_start)
            compliance = compute_compliance(current_plan, week_acts)
            parts.append(f"\n## This Week's Activities (Compliance: {compliance:.0f}%)\n{format_activities(week_acts)}")

    elif interaction_type == "daily_reminder":
        todays = extract_todays_session(current_plan) if current_plan else None
        if todays:
            parts.append(f"\n## Today's Session\n{json.dumps(todays, indent=2)}")
        last_act = await db.get_last_activity(telegram_id)
        if last_act:
            parts.append(f"\n## Last Run\n{format_activity(last_act)}")

    elif interaction_type == "assessment":
        pass  # Profile only

    elif interaction_type == "objective":
        recent = await db.get_recent_activities(telegram_id, limit=5)
        if recent:
            parts.append(f"\n## Recent Activities\n{format_activities(recent)}")

    else:
        # General Q&A
        parts.append(f"\n## Current Plan\n{format_plan(current_plan)}")
        recent = await db.get_recent_activities(telegram_id, limit=3)
        if recent:
            parts.append(f"\n## Recent Activities\n{format_activities(recent)}")

    return "\n".join(parts)
