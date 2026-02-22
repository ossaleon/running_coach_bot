import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Telegram
TELEGRAM_BOT_TOKEN: str = os.environ["TELEGRAM_BOT_TOKEN"]
BOT_PASSWORD: str = os.environ["BOT_PASSWORD"]

# Strava
STRAVA_CLIENT_ID: str = os.environ["STRAVA_CLIENT_ID"]
STRAVA_CLIENT_SECRET: str = os.environ["STRAVA_CLIENT_SECRET"]
STRAVA_VERIFY_TOKEN: str = os.environ["STRAVA_VERIFY_TOKEN"]

# Gemini
GEMINI_API_KEY: str = os.environ["GEMINI_API_KEY"]
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
GEMINI_THINKING_BUDGET: int = int(os.getenv("GEMINI_THINKING_BUDGET", "-1"))
GEMINI_MAX_OUTPUT_TOKENS: int = int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "8192"))
GEMINI_TEMPERATURE: float = float(os.getenv("GEMINI_TEMPERATURE", "0.7"))

# Server
PUBLIC_BASE_URL: str = os.environ["PUBLIC_BASE_URL"]
WEBHOOK_SERVER_HOST: str = os.getenv("WEBHOOK_SERVER_HOST", "0.0.0.0")
WEBHOOK_SERVER_PORT: int = int(os.getenv("WEBHOOK_SERVER_PORT", "8443"))

# Database
DATABASE_PATH: Path = Path(os.getenv("DATABASE_PATH", "./data/coach.db"))

# Coaching Defaults
DEFAULT_TIMEZONE: str = os.getenv("DEFAULT_TIMEZONE", "Europe/Rome")
DEFAULT_REMINDER_TIME: str = os.getenv("DEFAULT_REMINDER_TIME", "07:00")
WEEKLY_PLAN_DAY: int = int(os.getenv("WEEKLY_PLAN_DAY", "6"))
WEEKLY_PLAN_TIME: str = os.getenv("WEEKLY_PLAN_TIME", "19:00")
WEEKLY_REVIEW_TIME: str = os.getenv("WEEKLY_REVIEW_TIME", "10:00")
MAX_CONVERSATION_HISTORY: int = int(os.getenv("MAX_CONVERSATION_HISTORY", "10"))
CONVERSATION_RETENTION_DAYS: int = int(os.getenv("CONVERSATION_RETENTION_DAYS", "90"))
