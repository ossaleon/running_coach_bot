import logging
import secrets
import time
from urllib.parse import urlencode

import httpx

from config import STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, PUBLIC_BASE_URL

logger = logging.getLogger(__name__)

STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"

# Temporary nonce storage: {nonce: telegram_id}
_pending_nonces: dict[str, int] = {}


def generate_auth_url(telegram_id: int) -> str:
    nonce = secrets.token_urlsafe(16)
    _pending_nonces[nonce] = telegram_id
    params = {
        "client_id": STRAVA_CLIENT_ID,
        "redirect_uri": f"{PUBLIC_BASE_URL}/strava/callback",
        "response_type": "code",
        "approval_prompt": "auto",
        "scope": "read,activity:read_all",
        "state": f"{telegram_id}:{nonce}",
    }
    return f"{STRAVA_AUTH_URL}?{urlencode(params)}"


def validate_nonce(telegram_id: int, nonce: str) -> bool:
    stored = _pending_nonces.get(nonce)
    if stored == telegram_id:
        del _pending_nonces[nonce]
        return True
    return False


async def exchange_code(code: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            STRAVA_TOKEN_URL,
            data={
                "client_id": STRAVA_CLIENT_ID,
                "client_secret": STRAVA_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
            },
        )
        resp.raise_for_status()
        return resp.json()


async def refresh_access_token(refresh_token: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            STRAVA_TOKEN_URL,
            data={
                "client_id": STRAVA_CLIENT_ID,
                "client_secret": STRAVA_CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        resp.raise_for_status()
        return resp.json()


async def get_valid_token(user) -> str:
    """Get a valid access token, refreshing if expired."""
    if time.time() < (user.strava_token_expires or 0):
        return user.strava_access_token

    logger.info(f"Refreshing Strava token for user {user.telegram_id}")
    from db import database as db

    data = await refresh_access_token(user.strava_refresh_token)
    await db.refresh_strava_tokens(
        user.telegram_id,
        data["access_token"],
        data["refresh_token"],
        data["expires_at"],
    )
    return data["access_token"]
