import os
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, Update
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get allowed usernames from env
ALLOWED_USERNAMES = os.getenv("ALLOWED_USERNAMES", "").replace("@", "").split(",")
# Get maintenance mode status from env (default is off/"false")
MAINTENANCE_MODE = os.getenv("MAINTENANCE_MODE", "false").lower() in ["true", "1", "yes", "on"]

class RegistrationMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Any:
        # If maintenance mode is off, skip all checks
        if not MAINTENANCE_MODE:
            return await handler(event, data)
            
        # Check if it's a message or callback
        if isinstance(event, Message):
            username = event.from_user.username
            if username and username not in ALLOWED_USERNAMES:
                await event.answer(
                    "⚠️ O bot está em manutenção e disponível apenas para usuários autorizados.\n"
                    "Por favor, tente novamente mais tarde.",
                    parse_mode="Markdown"
                )
                return None
                
        elif isinstance(event, CallbackQuery):
            username = event.from_user.username
            if username and username not in ALLOWED_USERNAMES:
                await event.answer(
                    "⚠️ O bot está em manutenção e disponível apenas para usuários autorizados.",
                    show_alert=True
                )
                return None

        # If user is allowed or event type not handled, continue to next middleware/handler
        return await handler(event, data)