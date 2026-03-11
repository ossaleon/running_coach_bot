from dataclasses import dataclass, field
from typing import Optional


@dataclass
class User:
    telegram_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    is_authorized: bool = False
    authorized_at: Optional[str] = None
    strava_athlete_id: Optional[int] = None
    strava_access_token: Optional[str] = None
    strava_refresh_token: Optional[str] = None
    strava_token_expires: Optional[int] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    weekly_mileage_km: Optional[float] = None
    recent_race: Optional[str] = None
    injury_history: Optional[str] = None
    experience_level: Optional[str] = None
    preferred_days: Optional[str] = None
    max_hr: Optional[int] = None
    rest_hr: Optional[int] = None
    assessment_summary: Optional[str] = None
    objective_type: Optional[str] = None
    objective_target: Optional[str] = None
    objective_date: Optional[str] = None
    reminder_time: str = "07:00"
    timezone: str = "Europe/Rome"
    assessment_done: bool = False
    created_at: Optional[str] = None

    @property
    def has_strava(self) -> bool:
        return self.strava_athlete_id is not None

    @property
    def has_objective(self) -> bool:
        return self.objective_type is not None


@dataclass
class Activity:
    id: Optional[int] = None
    telegram_id: Optional[int] = None
    strava_activity_id: Optional[int] = None
    activity_type: Optional[str] = None
    name: Optional[str] = None
    start_date: Optional[str] = None
    distance_m: Optional[float] = None
    moving_time_s: Optional[int] = None
    elapsed_time_s: Optional[int] = None
    avg_speed_mps: Optional[float] = None
    max_speed_mps: Optional[float] = None
    avg_heartrate: Optional[float] = None
    max_heartrate: Optional[float] = None
    avg_cadence: Optional[float] = None
    total_elevation_m: Optional[float] = None
    suffer_score: Optional[int] = None
    splits_json: Optional[str] = None
    laps_json: Optional[str] = None
    description: Optional[str] = None
    ai_feedback: Optional[str] = None
    user_rpe: Optional[int] = None
    user_feedback: Optional[str] = None
    feedback_sent_at: Optional[str] = None
    created_at: Optional[str] = None

    @property
    def distance_km(self) -> float:
        return (self.distance_m or 0) / 1000.0

    @property
    def pace_min_per_km(self) -> Optional[str]:
        if not self.distance_m or not self.moving_time_s or self.distance_m == 0:
            return None
        pace_s = self.moving_time_s / (self.distance_m / 1000.0)
        minutes = int(pace_s // 60)
        seconds = int(pace_s % 60)
        return f"{minutes}:{seconds:02d}"

    @property
    def duration_formatted(self) -> str:
        if not self.moving_time_s:
            return "0:00"
        hours = self.moving_time_s // 3600
        minutes = (self.moving_time_s % 3600) // 60
        seconds = self.moving_time_s % 60
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"


@dataclass
class WeeklyPlan:
    id: Optional[int] = None
    telegram_id: Optional[int] = None
    week_start: Optional[str] = None
    plan_json: Optional[str] = None
    plan_text: Optional[str] = None
    review_text: Optional[str] = None
    compliance_pct: Optional[float] = None
    status: str = "active"
    created_at: Optional[str] = None


@dataclass
class Conversation:
    id: Optional[int] = None
    telegram_id: Optional[int] = None
    role: Optional[str] = None
    content: Optional[str] = None
    interaction_type: Optional[str] = None
    created_at: Optional[str] = None
