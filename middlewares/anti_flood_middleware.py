"""
Anti-Flood Middleware for Aiogram v3

This middleware tracks how many messages each user sends within a given
time window. If the user exceeds the allowed limit, any extra messages
are quietly ignored (not passed along to other handlers/routers).

Usage:
  1) Place this file in your `middlewares/` folder.
  2) Add `dp.message.middleware(AntiFloodMiddleware(...))` in your `main.py`.
"""

import time
import logging
from collections import deque
from typing import Dict, Deque, Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Update, Message

logger = logging.getLogger("bot.middleware.antiflood")

class AntiFloodMiddleware(BaseMiddleware):
    def __init__(self, limit: int = 5, interval: int = 10):
        """
        :param limit:    Max number of messages allowed per user in the interval
        :param interval: Time window in seconds
        """
        super().__init__()
        self.limit = limit
        self.interval = interval

        # user_messages keeps track of timestamps of recent messages per user_id
        # Example: { user_id: deque([timestamp1, timestamp2, ...]) }
        self.user_messages: Dict[int, Deque[float]] = {}

    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Any:
        """
        Intercepts incoming message updates:
          1) Checks how many messages the user has sent in the last `interval` seconds.
          2) If above `limit`, we skip calling the next handler (silently ignore).
          3) Otherwise, pass control to the next handler.
        """
        if isinstance(event, Message):
            user_id = event.from_user.id
            now = time.time()

            # Retrieve or create a new deque for this user
            timestamps = self.user_messages.setdefault(user_id, deque())

            # Drop timestamps older than `self.interval` seconds
            while timestamps and now - timestamps[0] > self.interval:
                timestamps.popleft()

            # Append the current message timestamp
            timestamps.append(now)

            if len(timestamps) > self.limit:
                # The user has exceeded the allowed limit in the given interval
                logger.warning(
                    f"[AntiFlood] User {user_id} is flooding: "
                    f"{len(timestamps)} messages within {self.interval}s (limit={self.limit})"
                )

                # Option A: Silently ignore the message (no next handler called)
                return

                # Option B: Send a warning message to the user. Example:
                # await event.answer("You're sending messages too fast! Please slow down.")
                # return

        # If not over limit, continue with the next handler in chain
        return await handler(event, data)
