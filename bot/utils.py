import logging

from telegram import Message
from telegram.constants import ParseMode
from telegram.error import BadRequest

logger = logging.getLogger(__name__)


async def reply_markdown(message: Message, text: str, **kwargs) -> Message:
    """Reply with Markdown, falling back to plain text on parse errors."""
    try:
        return await message.reply_text(text, parse_mode=ParseMode.MARKDOWN, **kwargs)
    except BadRequest:
        logger.debug("Markdown parse failed, sending as plain text")
        return await message.reply_text(text, **kwargs)


async def edit_markdown(callback_query, text: str, **kwargs) -> Message:
    """Edit message with Markdown, falling back to plain text on parse errors."""
    try:
        return await callback_query.edit_message_text(
            text, parse_mode=ParseMode.MARKDOWN, **kwargs
        )
    except BadRequest:
        logger.debug("Markdown parse failed, editing as plain text")
        return await callback_query.edit_message_text(text, **kwargs)


async def send_markdown(bot, chat_id: int, text: str, **kwargs) -> Message:
    """Send message with Markdown, falling back to plain text on parse errors."""
    try:
        return await bot.send_message(
            chat_id=chat_id, text=text, parse_mode=ParseMode.MARKDOWN, **kwargs
        )
    except BadRequest:
        logger.debug("Markdown parse failed, sending as plain text")
        return await bot.send_message(chat_id=chat_id, text=text, **kwargs)
