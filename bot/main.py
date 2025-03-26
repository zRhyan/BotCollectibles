import asyncio
import logging
import sys
import os
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
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
from commands.capturar import router as capturar_router
from admin_commands.addcarta import router as addcarta_router
from commands.admin import router as admin_router
from commands.pokebola import router as pokebola_router
from admin_commands.rclicar import router as rclicar_router

# Import the database 
from database.models import Base
from database.session import engine

# Middleware imports
from middlewares.logging_middleware import LoggingMiddleware
from middlewares.anti_flood_middleware import AntiFloodMiddleware

#------------------------------------------------------
# Teporary function to recreate the database schema
#------------------------------------------------------
from database.init_db import recreate_database

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
# Set the logging level for the middleware
logging.getLogger("aiogram.event").setLevel(logging.INFO)

# Register commands
dp.message.register(start_command, Command("start"))
dp.message.register(help_command, Command("help"))

#------------------------------------------------------
# Register routers
#------------------------------------------------------
dp.include_router(jornada_router)
dp.include_router(mochila_router)
dp.include_router(pokebanco_router)
dp.include_router(capturar_router)
dp.include_router(addcarta_router)
dp.include_router(admin_router)
dp.include_router(pokebola_router)
dp.include_router(rclicar_router)

# Register the middleware
dp.message.middleware(AntiFloodMiddleware(limit=5, interval=10))
dp.message.middleware(LoggingMiddleware())

#------------------------------------------------------
# Bot command menu
#------------------------------------------------------
async def set_bot_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="Iniciar o bot"),
        BotCommand(command="help", description="Obter ajuda sobre os comandos"),
        BotCommand(command="jornada", description="Registrar-se no bot"),
        BotCommand(command="mochila", description="Ver sua mochila"),
        BotCommand(command="pokebanco", description="Ver suas moedas e pokébolas"),
        BotCommand(command="capturar", description="Capturar um card"),
        BotCommand(command="addcarta", description="Adicionar um novo card (admin)"),
        BotCommand(command="pokebola", description="Exibir informações sobre um card"),
    ]
    await bot.set_my_commands(commands)

# Run the bot
async def main():
    # Comment this if you want to reset the database schema
    # await create_db()
    # print("Database schema created successfully!")

    # Recreate the database schema. Uncomment this if you want to reset the database schema
    await recreate_database()

    # Set bot commands
    await set_bot_commands(bot)

    # Start polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())