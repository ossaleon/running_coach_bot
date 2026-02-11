import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

STRAVA_API_BASE = "https://www.strava.com/api/v3"


async def get_activity(access_token: str, activity_id: int) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{STRAVA_API_BASE}/activities/{activity_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.json()


async def get_athlete(access_token: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{STRAVA_API_BASE}/athlete",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.json()


async def get_recent_activities(
    access_token: str, after_epoch: Optional[int] = None, per_page: int = 30
) -> list[dict]:
    params = {"per_page": per_page}
    if after_epoch:
        params["after"] = after_epoch
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{STRAVA_API_BASE}/athlete/activities",
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
        )
        resp.raise_for_status()
        return resp.json()
