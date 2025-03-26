from aiogram import BaseMiddleware
from aiogram.types import Message, Update
import logging

class LoggingMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: Update, data: dict):
        # Check if the event is a Message
        if isinstance(event, Message):
            # Extract user information
            user_id = event.from_user.id
            username = event.from_user.username or "NoUsername"
            command = event.text or "NoCommand"

            # Log the information
            logging.info(f"User @{username} (ID: {user_id}) sent command: {command}")

        # Call the next handler
        return await handler(event, data)