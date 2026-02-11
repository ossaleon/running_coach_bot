import asyncio
import logging

from aiohttp import web

from config import STRAVA_VERIFY_TOKEN
from db import database as db
from strava.client import get_activity
from strava.oauth import exchange_code, validate_nonce, get_valid_token

logger = logging.getLogger(__name__)


async def strava_webhook_validate(request: web.Request) -> web.Response:
    """GET /strava/webhook - Strava subscription validation."""
    mode = request.query.get("hub.mode")
    token = request.query.get("hub.verify_token")
    challenge = request.query.get("hub.challenge")

    if mode == "subscribe" and token == STRAVA_VERIFY_TOKEN:
        logger.info("Strava webhook subscription validated")
        return web.json_response({"hub.challenge": challenge})

    logger.warning(f"Strava webhook validation failed: mode={mode}")
    return web.Response(status=403, text="Forbidden")


async def strava_webhook_event(request: web.Request) -> web.Response:
    """POST /strava/webhook - Incoming activity events."""
    data = await request.json()
    logger.info(f"Strava webhook event: {data}")

    # Respond immediately (Strava requires 200 within 2 seconds)
    if (
        data.get("object_type") == "activity"
        and data.get("aspect_type") == "create"
    ):
        telegram_app = request.app.get("telegram_app")
        asyncio.create_task(
            _process_new_activity(
                data["owner_id"], data["object_id"], telegram_app
            )
        )

    return web.Response(status=200, text="OK")


async def _process_new_activity(
    strava_athlete_id: int, activity_id: int, telegram_app
) -> None:
    """Background task: fetch activity, get AI feedback, send to user."""
    try:
        user = await db.get_user_by_strava_id(strava_athlete_id)
        if not user:
            logger.warning(f"No user found for Strava athlete {strava_athlete_id}")
            return

        # Get valid token
        token = await get_valid_token(user)

        # Fetch full activity details
        activity_data = await get_activity(token, activity_id)

        # Only process running activities
        activity_type = activity_data.get("type", "")
        if activity_type not in ("Run", "TrailRun", "VirtualRun"):
            logger.info(f"Skipping non-run activity: {activity_type}")
            return

        # Store in database
        activity = await db.store_activity(user.telegram_id, activity_data)

        # Generate AI feedback
        from ai.coach import get_coaching_response

        distance_km = activity.distance_km
        pace = activity.pace_min_per_km
        duration = activity.duration_formatted
        hr_info = f", avg HR {activity.avg_heartrate:.0f}" if activity.avg_heartrate else ""

        user_msg = (
            f"I just completed a run: {distance_km:.1f} km in {duration} "
            f"(pace: {pace}/km{hr_info}). "
            f"Please analyze this run and give me feedback."
        )

        ai_feedback = await get_coaching_response(
            user.telegram_id, user_msg, "run_feedback"
        )

        # Store AI feedback
        await db.update_activity_feedback(activity.strava_activity_id, ai_feedback=ai_feedback)

        # Send feedback to user
        bot = telegram_app.bot
        await bot.send_message(
            chat_id=user.telegram_id,
            text=ai_feedback,
            parse_mode="Markdown",
        )

        # Ask for RPE
        from bot.keyboards import rpe_keyboard

        await bot.send_message(
            chat_id=user.telegram_id,
            text="How hard did that feel? Rate your perceived effort (1-10):",
            reply_markup=rpe_keyboard(),
        )

    except Exception:
        logger.exception(f"Error processing activity {activity_id} for athlete {strava_athlete_id}")


async def strava_oauth_callback(request: web.Request) -> web.Response:
    """GET /strava/callback - OAuth redirect handler."""
    code = request.query.get("code")
    state = request.query.get("state", "")
    error = request.query.get("error")

    if error:
        return web.Response(
            content_type="text/html",
            text="<html><body><h2>Authorization denied.</h2>"
            "<p>You can close this tab and return to Telegram.</p></body></html>",
        )

    try:
        telegram_id_str, nonce = state.split(":", 1)
        telegram_id = int(telegram_id_str)
    except (ValueError, AttributeError):
        return web.Response(status=400, text="Invalid state parameter")

    if not validate_nonce(telegram_id, nonce):
        return web.Response(status=400, text="Invalid or expired nonce")

    try:
        token_data = await exchange_code(code)
    except Exception:
        logger.exception("Failed to exchange Strava OAuth code")
        return web.Response(
            content_type="text/html",
            text="<html><body><h2>Authorization failed.</h2>"
            "<p>Please try again from Telegram with /linkstrava.</p></body></html>",
        )

    athlete = token_data.get("athlete", {})
    await db.update_strava_tokens(
        telegram_id=telegram_id,
        athlete_id=athlete["id"],
        access_token=token_data["access_token"],
        refresh_token=token_data["refresh_token"],
        expires_at=token_data["expires_at"],
    )

    # Notify user via Telegram
    telegram_app = request.app.get("telegram_app")
    if telegram_app:
        athlete_name = athlete.get("firstname", "")
        await telegram_app.bot.send_message(
            chat_id=telegram_id,
            text=(
                f"Strava account linked successfully! "
                f"Connected as {athlete_name}.\n\n"
                f"Next step: /assess to complete your fitness assessment."
            ),
        )

    return web.Response(
        content_type="text/html",
        text=(
            "<html><body>"
            "<h2>Strava connected!</h2>"
            "<p>You can close this tab and return to Telegram.</p>"
            "</body></html>"
        ),
    )
