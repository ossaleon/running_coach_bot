import asyncio
import logging
import signal

from aiohttp import web
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from config import (
    DATABASE_PATH,
    TELEGRAM_BOT_TOKEN,
    WEBHOOK_SERVER_HOST,
    WEBHOOK_SERVER_PORT,
)
from db import database as db
from db.database import set_db_path

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
# Reduce noise from httpx
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def register_handlers(application) -> None:
    """Register all bot handlers."""
    from bot.handlers.start import get_onboarding_handler
    from bot.handlers.assessment import get_assessment_handler
    from bot.handlers.objective import get_objective_handler
    from bot.handlers.feedback import get_feedback_handler, rpe_callback_handler
    from bot.handlers.strava_link import linkstrava_command
    from bot.handlers.plan import plan_command, newplan_command, plan_approval_callback, plan_feedback_handler
    from bot.handlers.settings import settings_command, settings_callback
    from bot.handlers.help import help_command, status_command

    # ConversationHandlers (highest priority)
    application.add_handler(get_onboarding_handler())
    application.add_handler(get_assessment_handler())
    application.add_handler(get_objective_handler())
    application.add_handler(get_feedback_handler())

    # Command handlers
    application.add_handler(CommandHandler("linkstrava", linkstrava_command))
    application.add_handler(CommandHandler("plan", plan_command))
    application.add_handler(CommandHandler("newplan", newplan_command))
    application.add_handler(CommandHandler("settings", settings_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("help", help_command))

    # Callback query handlers
    application.add_handler(
        CallbackQueryHandler(settings_callback, pattern=r"^settings_")
    )
    application.add_handler(
        CallbackQueryHandler(rpe_callback_handler, pattern=r"^rpe_")
    )
    application.add_handler(
        CallbackQueryHandler(plan_approval_callback, pattern=r"^plan_")
    )

    # General text handler (catch-all for settings text and general messages)
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, general_message_handler)
    )


async def general_message_handler(update, context) -> None:
    """Handle general text messages."""
    from bot.handlers.settings import handle_settings_text

    # Check if this is plan feedback (after rejection)
    from bot.handlers.plan import plan_feedback_handler
    telegram_id = update.effective_user.id
    if context.bot_data.get(f"plan_feedback_pending_{telegram_id}"):
        await plan_feedback_handler(update, context)
        return

    # Check if this is a settings text input
    if await handle_settings_text(update, context):
        return

    # Check if user has pending run comments
    activity_id = context.user_data.get("pending_run_comments")
    if activity_id:
        await db.update_activity_feedback(
            strava_activity_id=activity_id,
            user_feedback=update.message.text.strip(),
        )
        context.user_data.pop("pending_run_comments", None)
        await update.message.reply_text("Comment recorded. Thanks!")
        return

    # Check authorization
    user = await db.get_user(update.effective_user.id)
    if not user or not user.is_authorized:
        await update.message.reply_text("Please use /start to authenticate first.")
        return

    # General coaching Q&A
    from ai.coach import get_coaching_response

    response = await get_coaching_response(
        update.effective_user.id, update.message.text, "general"
    )
    from bot.utils import reply_markdown

    await reply_markdown(update.message, response)


async def error_handler(update, context) -> None:
    """Global error handler — log the error and notify the user."""
    logger.error("Unhandled exception:", exc_info=context.error)

    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "Something went wrong. Please try again."
            )
        except Exception:
            pass


async def main() -> None:
    # Set database path
    set_db_path(DATABASE_PATH)

    # Initialize database
    await db.init_db()
    logger.info("Database initialized")

    # Build Telegram bot application
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    register_handlers(application)
    application.add_error_handler(error_handler)

    # Set up aiohttp web server for Strava webhooks and OAuth
    from strava.webhook import (
        strava_oauth_callback,
        strava_webhook_event,
        strava_webhook_validate,
    )

    aiohttp_app = web.Application()
    aiohttp_app.router.add_get("/strava/webhook", strava_webhook_validate)
    aiohttp_app.router.add_post("/strava/webhook", strava_webhook_event)
    aiohttp_app.router.add_get("/strava/callback", strava_oauth_callback)
    aiohttp_app["telegram_app"] = application

    runner = web.AppRunner(aiohttp_app)
    await runner.setup()
    site = web.TCPSite(runner, WEBHOOK_SERVER_HOST, WEBHOOK_SERVER_PORT)

    # Start aiohttp server
    await site.start()
    logger.info(f"Webhook server listening on {WEBHOOK_SERVER_HOST}:{WEBHOOK_SERVER_PORT}")

    # Initialize and start the telegram bot (retry until network is available)
    await application.initialize()
    await application.start()
    for attempt in range(1, 61):
        try:
            await application.updater.start_polling(drop_pending_updates=True)
            break
        except Exception as e:
            logger.warning(f"Polling start failed (attempt {attempt}/60): {e}")
            await asyncio.sleep(10)
    else:
        logger.error("Failed to start polling after 60 attempts, exiting")
        return
    logger.info("Telegram bot started (polling)")

    # Restore scheduled jobs for all authorized users
    from scheduler.jobs import schedule_user_jobs

    users = await db.get_all_authorized_users()
    for user in users:
        await schedule_user_jobs(application, user.telegram_id)
    logger.info(f"Restored scheduled jobs for {len(users)} authorized user(s)")

    # Schedule periodic conversation cleanup
    from config import CONVERSATION_RETENTION_DAYS

    async def cleanup_job(context) -> None:
        count = await db.cleanup_old_conversations(CONVERSATION_RETENTION_DAYS)
        if count:
            logger.info(f"Cleaned up {count} old conversation entries")

    application.job_queue.run_repeating(
        cleanup_job, interval=86400, first=3600, name="cleanup_conversations"
    )

    logger.info("Bot is fully operational.")

    # Wait for shutdown signal
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _signal_handler():
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    await stop_event.wait()

    # Graceful shutdown
    logger.info("Shutting down...")
    await application.updater.stop()
    await application.stop()
    await application.shutdown()
    await runner.cleanup()
    logger.info("Shutdown complete.")


if __name__ == "__main__":
    asyncio.run(main())
