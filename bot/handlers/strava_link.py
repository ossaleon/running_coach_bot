from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from db import database as db
from strava.oauth import generate_auth_url


async def linkstrava_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await db.get_user(update.effective_user.id)
    if not user or not user.is_authorized:
        await update.message.reply_text("Please use /start to authenticate first.")
        return

    if user.has_strava:
        await update.message.reply_text(
            "Your Strava account is already linked!\n"
            "If you need to relink, just click the button below.",
        )

    auth_url = generate_auth_url(update.effective_user.id)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Connect Strava", url=auth_url)]
    ])
    await update.message.reply_text(
        "Click the button below to connect your Strava account.\n"
        "You'll be redirected to Strava to authorize access.",
        reply_markup=keyboard,
    )
