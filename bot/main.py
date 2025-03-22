import asyncio
import logging
import sys
import os
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from dotenv import load_dotenv

# Add the root directory to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import routers
from commands.help import help_command
from commands.start import start_command
from commands.jornada import router as jornada_router

from database.models import Base
from database.session import engine

# Function to create the database schema
async def create_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Configure the bot
bot = Bot(token=BOT_TOKEN)

# Initialize the Dispatcher
dp = Dispatcher()

# Logger (for debugging)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)

# Register commands
dp.message.register(start_command, Command("start"))
dp.message.register(help_command, Command("help"))

# Include the jornada router
dp.include_router(jornada_router)

# Run the bot
async def main():
    # Initialize the database schema
    await create_db()
    print("Database schema created successfully!")

    # Start polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())