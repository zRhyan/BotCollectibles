import os
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get allowed usernames from env
ALLOWED_USERNAMES = os.getenv("ALLOWED_USERNAMES", "").replace("@", "").split(",")

class RegistrationMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        # Only check for /jornada command
        if event.text and event.text.startswith("/jornada"):
            # Get username without @ if it exists
            username = event.from_user.username

            # Check if user is in allowed list
            if username and username not in ALLOWED_USERNAMES:
                await event.answer(
                    "⚠️ Desculpe, mas o registro no bot está temporariamente restrito a usuários autorizados.",
                    parse_mode="Markdown"
                )
                return None

        # If not /jornada command or user is allowed, continue to next middleware/handler
        return await handler(event, data)