CREATE TABLE IF NOT EXISTS users (
    telegram_id         INTEGER PRIMARY KEY,
    username            TEXT,
    first_name          TEXT,
    is_authorized       INTEGER DEFAULT 0,
    authorized_at       TEXT,
    -- Strava
    strava_athlete_id   INTEGER UNIQUE,
    strava_access_token TEXT,
    strava_refresh_token TEXT,
    strava_token_expires INTEGER,
    -- Profile
    age                 INTEGER,
    gender              TEXT,
    weekly_mileage_km   REAL,
    recent_race         TEXT,
    injury_history      TEXT,
    experience_level    TEXT,
    preferred_days      TEXT,
    max_hr              INTEGER,
    rest_hr             INTEGER,
    -- Objective
    objective_type      TEXT,
    objective_target    TEXT,
    objective_date      TEXT,
    -- Settings
    reminder_time       TEXT DEFAULT '07:00',
    timezone            TEXT DEFAULT 'Europe/Rome',
    -- State tracking
    assessment_done     INTEGER DEFAULT 0,
    created_at          TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS activities (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id         INTEGER REFERENCES users(telegram_id),
    strava_activity_id  INTEGER UNIQUE,
    activity_type       TEXT,
    name                TEXT,
    start_date          TEXT,
    distance_m          REAL,
    moving_time_s       INTEGER,
    elapsed_time_s      INTEGER,
    avg_speed_mps       REAL,
    max_speed_mps       REAL,
    avg_heartrate       REAL,
    max_heartrate       REAL,
    avg_cadence         REAL,
    total_elevation_m   REAL,
    suffer_score        INTEGER,
    splits_json         TEXT,
    laps_json           TEXT,
    description         TEXT,
    ai_feedback         TEXT,
    user_rpe            INTEGER,
    user_feedback       TEXT,
    feedback_sent_at    TEXT,
    created_at          TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS weekly_plans (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id         INTEGER REFERENCES users(telegram_id),
    week_start          TEXT,
    plan_json           TEXT,
    plan_text           TEXT,
    review_text         TEXT,
    compliance_pct      REAL,
    status              TEXT DEFAULT 'active',
    created_at          TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS conversations (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id         INTEGER REFERENCES users(telegram_id),
    role                TEXT,
    content             TEXT,
    interaction_type    TEXT,
    created_at          TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_activities_user ON activities(telegram_id, start_date);
CREATE INDEX IF NOT EXISTS idx_plans_user ON weekly_plans(telegram_id, week_start);
CREATE INDEX IF NOT EXISTS idx_convos_user ON conversations(telegram_id, created_at);
