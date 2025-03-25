import asyncio
import logging
import sys
import os
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from dotenv import load_dotenv

# Add the root directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Import routers
from commands.help import help_command
from commands.start import start_command
from commands.jornada import router as jornada_router
from commands.mochila import router as mochila_router
from commands.pokebanco import router as pokebanco_router

from database.models import Base
from database.session import engine

#Temporary import for recreate database and temporary function call
from database.init_db import recreate_database
async def main():
    await recreate_database()  # Just once!
    await dp.start_polling(bot)

# Function to create the database schema
async def create_db():
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("Database schema created successfully!")
    except Exception as e:
        print(f"Failed to create database schema: {e}")

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

#------------------------------------------------------
# Register routers
#------------------------------------------------------
dp.include_router(jornada_router)
dp.include_router(mochila_router)
dp.include_router(pokebanco_router)

# Run the bot
async def main():
    # Initialize the database schema
    await create_db()
    print("Database schema created successfully!")

    # Start polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())