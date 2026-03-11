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
    if user.assessment_summary:
        parts.append(f"\nAssessment analysis:\n{user.assessment_summary}")
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
    """Compute compliance by matching activities to planned sessions by distance (±20%).

    Day-independent: matches planned sessions to actual activities greedily by
    closest distance within 20% tolerance. Each activity matches at most one session.
    """
    if not plan or not plan.plan_json:
        return 0.0
    try:
        data = json.loads(plan.plan_json)
        sessions = data.get("sessions", [])
        planned = [s for s in sessions if s.get("type", "").lower() != "rest"]
        if not planned:
            return 100.0

        # Build list of planned distances (km)
        planned_distances = []
        for s in planned:
            d = s.get("distance_km", 0)
            if isinstance(d, (int, float)) and d > 0:
                planned_distances.append(d)
            else:
                planned_distances.append(0)

        # Build list of actual distances
        actual_distances = [act.distance_km for act in activities if act.distance_km > 0]

        # Greedy match: sort planned by distance descending, match closest actual within 20%
        matched = 0
        remaining_actual = list(actual_distances)
        for planned_d in sorted(planned_distances, reverse=True):
            if planned_d == 0:
                # Session without distance (e.g., strength) — match if any activity exists
                if remaining_actual:
                    remaining_actual.pop()
                    matched += 1
                continue
            tolerance = planned_d * 0.2
            best_idx = None
            best_diff = float("inf")
            for i, actual_d in enumerate(remaining_actual):
                diff = abs(actual_d - planned_d)
                if diff <= tolerance and diff < best_diff:
                    best_diff = diff
                    best_idx = i
            if best_idx is not None:
                remaining_actual.pop(best_idx)
                matched += 1

        return (matched / len(planned)) * 100.0
    except (json.JSONDecodeError, KeyError):
        return 0.0


def compute_performance_summary(activities: list[Activity]) -> str:
    """Compute weekly mileage trends, pace trends, and current fitness signals."""
    if not activities:
        return ""

    # Group activities by week
    weeks = {}
    for act in activities:
        if not act.start_date or not act.distance_m:
            continue
        try:
            dt = datetime.fromisoformat(act.start_date)
            # Use ISO week for grouping
            week_key = dt.strftime("%Y-W%W")
            if week_key not in weeks:
                weeks[week_key] = {"distance_km": 0, "runs": 0, "paces": [], "hrs": []}
            w = weeks[week_key]
            w["distance_km"] += act.distance_km
            w["runs"] += 1
            if act.moving_time_s and act.distance_m > 0:
                pace_s = act.moving_time_s / (act.distance_m / 1000.0)
                w["paces"].append(pace_s)
            if act.avg_heartrate:
                w["hrs"].append(act.avg_heartrate)
        except ValueError:
            continue

    if not weeks:
        return ""

    # Sort weeks chronologically and take last 4
    sorted_weeks = sorted(weeks.items())[-4:]

    parts = ["*Performance Trends (last 4 weeks):*"]
    for week_key, w in sorted_weeks:
        avg_pace_s = sum(w["paces"]) / len(w["paces"]) if w["paces"] else 0
        pace_min = int(avg_pace_s // 60)
        pace_sec = int(avg_pace_s % 60)
        avg_hr = sum(w["hrs"]) / len(w["hrs"]) if w["hrs"] else 0
        line = f"  {week_key}: {w['distance_km']:.1f} km over {w['runs']} runs, avg pace {pace_min}:{pace_sec:02d}/km"
        if avg_hr:
            line += f", avg HR {avg_hr:.0f}"
        parts.append(line)

    # Mileage trend
    volumes = [w["distance_km"] for _, w in sorted_weeks]
    if len(volumes) >= 2:
        recent_avg = sum(volumes[-2:]) / 2
        parts.append(f"Current weekly average: {recent_avg:.1f} km")

    return "\n".join(parts)


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
        recent = await db.get_recent_activities(telegram_id, limit=20)
        if recent:
            parts.append(f"\n## Recent Activities\n{format_activities(recent[:10])}")
            perf_summary = compute_performance_summary(recent)
            if perf_summary:
                parts.append(f"\n## {perf_summary}")

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
