import logging

from google import genai
from google.genai import types

from ai.context import build_context
from ai.prompts import SYSTEM_PROMPT
from config import (
    GEMINI_API_KEY,
    GEMINI_MAX_OUTPUT_TOKENS,
    GEMINI_MODEL,
    GEMINI_TEMPERATURE,
    GEMINI_THINKING_LEVEL,
    MAX_CONVERSATION_HISTORY,
)
from db import database as db

logger = logging.getLogger(__name__)

_client: genai.Client = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


async def get_coaching_response(
    telegram_id: int,
    user_message: str,
    interaction_type: str,
) -> str:
    """Get a coaching response from Gemini with full context."""
    client = _get_client()

    # Build context
    context_str = await build_context(telegram_id, interaction_type)

    # Load conversation history
    history = await db.get_recent_conversations(
        telegram_id, limit=MAX_CONVERSATION_HISTORY
    )
    chat_history = []
    for msg in history:
        role = "user" if msg.role == "user" else "model"
        chat_history.append(
            types.Content(role=role, parts=[types.Part(text=msg.content)])
        )

    # Build augmented message with context
    augmented_message = (
        f"CONTEXT (do not repeat this back to the user):\n{context_str}\n\n---\n\n"
        f"INTERACTION TYPE: {interaction_type}\n\n"
        f"USER MESSAGE: {user_message}"
    )

    # Map thinking level from config (NONE disables thinking)
    thinking_level = GEMINI_THINKING_LEVEL.upper() if GEMINI_THINKING_LEVEL else "NONE"
    thinking_config = (
        types.ThinkingConfig(thinking_level=thinking_level)
        if thinking_level in ("HIGH", "LOW")
        else None
    )

    try:
        response = await client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=chat_history
            + [
                types.Content(
                    role="user", parts=[types.Part(text=augmented_message)]
                )
            ],
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                thinking_config=thinking_config,
                max_output_tokens=GEMINI_MAX_OUTPUT_TOKENS,
                temperature=GEMINI_TEMPERATURE,
            ),
        )

        assistant_text = response.text

    except Exception:
        logger.exception("Gemini API call failed")
        assistant_text = (
            "I'm having trouble processing that right now. "
            "Please try again in a moment."
        )

    # Store conversation
    await db.store_conversation(telegram_id, "user", user_message, interaction_type)
    await db.store_conversation(
        telegram_id, "assistant", assistant_text, interaction_type
    )

    return assistant_text
