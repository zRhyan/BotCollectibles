import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv
import os

# Import routers
from commands.help import help_command
from commands.start import start_command
from commands.jornada import router as jornada_router

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Configure the bot
bot = Bot(token=BOT_TOKEN)

# Initialize FSM storage
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Logger (for debugging)
logging.basicConfig(level=logging.INFO)

# Register commands
dp.message.register(start_command, Command("start"))
dp.message.register(help_command, Command("help"))

# Include the jornada router
dp.include_router(jornada_router)

# Run the bot
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())