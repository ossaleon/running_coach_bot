import aiosqlite
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from db.models import User, Activity, WeeklyPlan, Conversation

logger = logging.getLogger(__name__)

_db_path: Path = Path("./data/coach.db")


def set_db_path(path: Path) -> None:
    global _db_path
    _db_path = path


async def _get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(_db_path)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


async def init_db() -> None:
    _db_path.parent.mkdir(parents=True, exist_ok=True)
    schema_path = Path(__file__).parent / "schema.sql"
    schema = schema_path.read_text()
    db = await _get_db()
    try:
        await db.executescript(schema)
        await db.commit()
    finally:
        await db.close()
    logger.info(f"Database initialized at {_db_path}")


def _row_to_user(row: aiosqlite.Row) -> User:
    return User(
        telegram_id=row["telegram_id"],
        username=row["username"],
        first_name=row["first_name"],
        is_authorized=bool(row["is_authorized"]),
        authorized_at=row["authorized_at"],
        strava_athlete_id=row["strava_athlete_id"],
        strava_access_token=row["strava_access_token"],
        strava_refresh_token=row["strava_refresh_token"],
        strava_token_expires=row["strava_token_expires"],
        age=row["age"],
        gender=row["gender"],
        weekly_mileage_km=row["weekly_mileage_km"],
        recent_race=row["recent_race"],
        injury_history=row["injury_history"],
        experience_level=row["experience_level"],
        preferred_days=row["preferred_days"],
        max_hr=row["max_hr"],
        rest_hr=row["rest_hr"],
        objective_type=row["objective_type"],
        objective_target=row["objective_target"],
        objective_date=row["objective_date"],
        reminder_time=row["reminder_time"] or "07:00",
        timezone=row["timezone"] or "Europe/Rome",
        assessment_done=bool(row["assessment_done"]),
        created_at=row["created_at"],
    )


def _row_to_activity(row: aiosqlite.Row) -> Activity:
    return Activity(
        id=row["id"],
        telegram_id=row["telegram_id"],
        strava_activity_id=row["strava_activity_id"],
        activity_type=row["activity_type"],
        name=row["name"],
        start_date=row["start_date"],
        distance_m=row["distance_m"],
        moving_time_s=row["moving_time_s"],
        elapsed_time_s=row["elapsed_time_s"],
        avg_speed_mps=row["avg_speed_mps"],
        max_speed_mps=row["max_speed_mps"],
        avg_heartrate=row["avg_heartrate"],
        max_heartrate=row["max_heartrate"],
        avg_cadence=row["avg_cadence"],
        total_elevation_m=row["total_elevation_m"],
        suffer_score=row["suffer_score"],
        splits_json=row["splits_json"],
        laps_json=row["laps_json"],
        description=row["description"],
        ai_feedback=row["ai_feedback"],
        user_rpe=row["user_rpe"],
        user_feedback=row["user_feedback"],
        feedback_sent_at=row["feedback_sent_at"],
        created_at=row["created_at"],
    )


def _row_to_plan(row: aiosqlite.Row) -> WeeklyPlan:
    return WeeklyPlan(
        id=row["id"],
        telegram_id=row["telegram_id"],
        week_start=row["week_start"],
        plan_json=row["plan_json"],
        plan_text=row["plan_text"],
        review_text=row["review_text"],
        compliance_pct=row["compliance_pct"],
        status=row["status"],
        created_at=row["created_at"],
    )


def _row_to_conversation(row: aiosqlite.Row) -> Conversation:
    return Conversation(
        id=row["id"],
        telegram_id=row["telegram_id"],
        role=row["role"],
        content=row["content"],
        interaction_type=row["interaction_type"],
        created_at=row["created_at"],
    )


# ── User CRUD ──

async def get_user(telegram_id: int) -> Optional[User]:
    db = await _get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        )
        row = await cursor.fetchone()
        return _row_to_user(row) if row else None
    finally:
        await db.close()


async def create_user(telegram_id: int, username: str = None, first_name: str = None) -> User:
    db = await _get_db()
    try:
        await db.execute(
            "INSERT OR IGNORE INTO users (telegram_id, username, first_name) VALUES (?, ?, ?)",
            (telegram_id, username, first_name),
        )
        await db.commit()
    finally:
        await db.close()
    return await get_user(telegram_id)


async def authorize_user(telegram_id: int) -> None:
    db = await _get_db()
    try:
        await db.execute(
            "UPDATE users SET is_authorized = 1, authorized_at = datetime('now') WHERE telegram_id = ?",
            (telegram_id,),
        )
        await db.commit()
    finally:
        await db.close()


async def get_all_authorized_users() -> list[User]:
    db = await _get_db()
    try:
        cursor = await db.execute("SELECT * FROM users WHERE is_authorized = 1")
        rows = await cursor.fetchall()
        return [_row_to_user(r) for r in rows]
    finally:
        await db.close()


async def get_user_by_strava_id(strava_athlete_id: int) -> Optional[User]:
    db = await _get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM users WHERE strava_athlete_id = ?", (strava_athlete_id,)
        )
        row = await cursor.fetchone()
        return _row_to_user(row) if row else None
    finally:
        await db.close()


async def update_strava_tokens(
    telegram_id: int,
    athlete_id: int,
    access_token: str,
    refresh_token: str,
    expires_at: int,
) -> None:
    db = await _get_db()
    try:
        await db.execute(
            """UPDATE users SET
                strava_athlete_id = ?,
                strava_access_token = ?,
                strava_refresh_token = ?,
                strava_token_expires = ?
            WHERE telegram_id = ?""",
            (athlete_id, access_token, refresh_token, expires_at, telegram_id),
        )
        await db.commit()
    finally:
        await db.close()


async def refresh_strava_tokens(
    telegram_id: int, access_token: str, refresh_token: str, expires_at: int
) -> None:
    db = await _get_db()
    try:
        await db.execute(
            """UPDATE users SET
                strava_access_token = ?,
                strava_refresh_token = ?,
                strava_token_expires = ?
            WHERE telegram_id = ?""",
            (access_token, refresh_token, expires_at, telegram_id),
        )
        await db.commit()
    finally:
        await db.close()


async def update_user_profile(telegram_id: int, **kwargs) -> None:
    if not kwargs:
        return
    allowed = {
        "age", "gender", "weekly_mileage_km", "recent_race", "injury_history",
        "experience_level", "preferred_days", "max_hr", "rest_hr",
        "assessment_done", "reminder_time", "timezone",
    }
    filtered = {k: v for k, v in kwargs.items() if k in allowed}
    if not filtered:
        return
    set_clause = ", ".join(f"{k} = ?" for k in filtered)
    values = list(filtered.values()) + [telegram_id]
    db = await _get_db()
    try:
        await db.execute(
            f"UPDATE users SET {set_clause} WHERE telegram_id = ?", values
        )
        await db.commit()
    finally:
        await db.close()


async def update_user_objective(
    telegram_id: int, objective_type: str, objective_target: str, objective_date: str
) -> None:
    db = await _get_db()
    try:
        await db.execute(
            """UPDATE users SET
                objective_type = ?, objective_target = ?, objective_date = ?
            WHERE telegram_id = ?""",
            (objective_type, objective_target, objective_date, telegram_id),
        )
        await db.commit()
    finally:
        await db.close()


# ── Activity CRUD ──

async def store_activity(telegram_id: int, data: dict) -> Activity:
    db = await _get_db()
    try:
        await db.execute(
            """INSERT OR REPLACE INTO activities
                (telegram_id, strava_activity_id, activity_type, name, start_date,
                 distance_m, moving_time_s, elapsed_time_s, avg_speed_mps, max_speed_mps,
                 avg_heartrate, max_heartrate, avg_cadence, total_elevation_m,
                 suffer_score, splits_json, laps_json, description)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                telegram_id,
                data.get("id"),
                data.get("type"),
                data.get("name"),
                data.get("start_date_local"),
                data.get("distance"),
                data.get("moving_time"),
                data.get("elapsed_time"),
                data.get("average_speed"),
                data.get("max_speed"),
                data.get("average_heartrate"),
                data.get("max_heartrate"),
                data.get("average_cadence"),
                data.get("total_elevation_gain"),
                data.get("suffer_score"),
                json.dumps(data.get("splits_metric")) if data.get("splits_metric") else None,
                json.dumps(data.get("laps")) if data.get("laps") else None,
                data.get("description"),
            ),
        )
        await db.commit()
    finally:
        await db.close()

    return await get_activity_by_strava_id(data["id"])


async def get_activity_by_strava_id(strava_activity_id: int) -> Optional[Activity]:
    db = await _get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM activities WHERE strava_activity_id = ?",
            (strava_activity_id,),
        )
        row = await cursor.fetchone()
        return _row_to_activity(row) if row else None
    finally:
        await db.close()


async def get_recent_activities(telegram_id: int, limit: int = 5) -> list[Activity]:
    db = await _get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM activities WHERE telegram_id = ? ORDER BY start_date DESC LIMIT ?",
            (telegram_id, limit),
        )
        rows = await cursor.fetchall()
        return [_row_to_activity(r) for r in rows]
    finally:
        await db.close()


async def get_activities_for_week(telegram_id: int, week_start: str) -> list[Activity]:
    week_end = (
        datetime.fromisoformat(week_start) + timedelta(days=7)
    ).isoformat()
    db = await _get_db()
    try:
        cursor = await db.execute(
            """SELECT * FROM activities
            WHERE telegram_id = ? AND start_date >= ? AND start_date < ?
            ORDER BY start_date""",
            (telegram_id, week_start, week_end),
        )
        rows = await cursor.fetchall()
        return [_row_to_activity(r) for r in rows]
    finally:
        await db.close()


async def get_last_activity(telegram_id: int) -> Optional[Activity]:
    db = await _get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM activities WHERE telegram_id = ? ORDER BY start_date DESC LIMIT 1",
            (telegram_id,),
        )
        row = await cursor.fetchone()
        return _row_to_activity(row) if row else None
    finally:
        await db.close()


async def update_activity_feedback(
    strava_activity_id: int, ai_feedback: str = None, user_rpe: int = None, user_feedback: str = None
) -> None:
    db = await _get_db()
    try:
        updates = []
        values = []
        if ai_feedback is not None:
            updates.append("ai_feedback = ?")
            values.append(ai_feedback)
            updates.append("feedback_sent_at = datetime('now')")
        if user_rpe is not None:
            updates.append("user_rpe = ?")
            values.append(user_rpe)
        if user_feedback is not None:
            updates.append("user_feedback = ?")
            values.append(user_feedback)
        if not updates:
            return
        values.append(strava_activity_id)
        await db.execute(
            f"UPDATE activities SET {', '.join(updates)} WHERE strava_activity_id = ?",
            values,
        )
        await db.commit()
    finally:
        await db.close()


# ── Weekly Plans CRUD ──

async def get_active_plan(telegram_id: int) -> Optional[WeeklyPlan]:
    db = await _get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM weekly_plans WHERE telegram_id = ? AND status = 'active' ORDER BY week_start DESC LIMIT 1",
            (telegram_id,),
        )
        row = await cursor.fetchone()
        return _row_to_plan(row) if row else None
    finally:
        await db.close()


async def get_last_completed_plan(telegram_id: int) -> Optional[WeeklyPlan]:
    db = await _get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM weekly_plans WHERE telegram_id = ? AND status = 'completed' ORDER BY week_start DESC LIMIT 1",
            (telegram_id,),
        )
        row = await cursor.fetchone()
        return _row_to_plan(row) if row else None
    finally:
        await db.close()


async def create_weekly_plan(
    telegram_id: int, week_start: str, plan_json: str, plan_text: str
) -> WeeklyPlan:
    db = await _get_db()
    try:
        cursor = await db.execute(
            """INSERT INTO weekly_plans (telegram_id, week_start, plan_json, plan_text)
            VALUES (?, ?, ?, ?)""",
            (telegram_id, week_start, plan_json, plan_text),
        )
        plan_id = cursor.lastrowid
        await db.commit()
    finally:
        await db.close()
    db = await _get_db()
    try:
        cursor = await db.execute("SELECT * FROM weekly_plans WHERE id = ?", (plan_id,))
        row = await cursor.fetchone()
        return _row_to_plan(row)
    finally:
        await db.close()


async def complete_current_plan(telegram_id: int) -> None:
    db = await _get_db()
    try:
        await db.execute(
            "UPDATE weekly_plans SET status = 'completed' WHERE telegram_id = ? AND status = 'active'",
            (telegram_id,),
        )
        await db.commit()
    finally:
        await db.close()


async def update_plan_review(plan_id: int, review_text: str, compliance_pct: float = None) -> None:
    db = await _get_db()
    try:
        if compliance_pct is not None:
            await db.execute(
                "UPDATE weekly_plans SET review_text = ?, compliance_pct = ? WHERE id = ?",
                (review_text, compliance_pct, plan_id),
            )
        else:
            await db.execute(
                "UPDATE weekly_plans SET review_text = ? WHERE id = ?",
                (review_text, plan_id),
            )
        await db.commit()
    finally:
        await db.close()


# ── Conversations CRUD ──

async def store_conversation(
    telegram_id: int, role: str, content: str, interaction_type: str
) -> None:
    db = await _get_db()
    try:
        await db.execute(
            "INSERT INTO conversations (telegram_id, role, content, interaction_type) VALUES (?, ?, ?, ?)",
            (telegram_id, role, content, interaction_type),
        )
        await db.commit()
    finally:
        await db.close()


async def get_recent_conversations(
    telegram_id: int, limit: int = 10, interaction_types: list[str] = None
) -> list[Conversation]:
    db = await _get_db()
    try:
        if interaction_types:
            placeholders = ", ".join("?" for _ in interaction_types)
            cursor = await db.execute(
                f"""SELECT * FROM conversations
                WHERE telegram_id = ? AND interaction_type IN ({placeholders})
                ORDER BY created_at DESC LIMIT ?""",
                [telegram_id] + interaction_types + [limit],
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM conversations WHERE telegram_id = ? ORDER BY created_at DESC LIMIT ?",
                (telegram_id, limit),
            )
        rows = await cursor.fetchall()
        return [_row_to_conversation(r) for r in reversed(rows)]
    finally:
        await db.close()


async def cleanup_old_conversations(days: int = 90) -> int:
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    db = await _get_db()
    try:
        cursor = await db.execute(
            "DELETE FROM conversations WHERE created_at < ?", (cutoff,)
        )
        count = cursor.rowcount
        await db.commit()
        return count
    finally:
        await db.close()
