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
from commands.admin import router as admin_router
from commands.pokebola import router as pokebola_router
from commands.pokemart import router as pokemart_router
from commands.comprarbolas import router as comprarbolas_router
from commands.doarcards import router as doarcards_router
from commands.doarbolas import router as doarbolas_router
from commands.doarcoins import router as doarcoins_router
from commands.venderc import router as venderc_router
from commands.roubar import router as roubar_router
from commands.pokedex import router as pokedex_router
from commands.favpoke import router as favpoke_router
from commands.ginasio import router as ginasio_router

from admin_commands.addcarta import router as addcarta_router
from admin_commands.rclicar import router as rclicar_router
from admin_commands.rcoins import router as rcoins_router
from admin_commands.imgpd import router as imgpd_router

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
dp.include_router(pokedex_router)
dp.include_router(mochila_router)
dp.include_router(pokebanco_router)
dp
dp.include_router(capturar_router)
dp.include_router(addcarta_router)
dp.include_router(favpoke_router)
dp.include_router(imgpd_router)
dp.include_router(admin_router)
dp.include_router(pokebola_router)
dp.include_router(rclicar_router)
dp.include_router(rcoins_router)
dp.include_router(comprarbolas_router)
dp.include_router(doarcards_router)
dp.include_router(doarbolas_router)
dp.include_router(doarcoins_router)
dp.include_router(venderc_router) #Before pokemart. If it work I'm a happy man.
dp.include_router(roubar_router)
dp.include_router(pokemart_router)


# Register the middleware
dp.message.middleware(AntiFloodMiddleware(limit=5, interval=10))
dp.message.middleware(LoggingMiddleware())

#------------------------------------------------------
# Bot command menu
#------------------------------------------------------
from sqlalchemy.future import select
from database.session import get_session
from database.models import User

async def set_bot_commands(bot: Bot):
    # General commands for all users
    commands = [
        BotCommand(command="start", description="Iniciar o bot"),
        BotCommand(command="help", description="Obter ajuda sobre os comandos"),
        BotCommand(command="jornada", description="Registrar-se no bot"),
        BotCommand(command="mochila", description="Ver sua mochila"),
        BotCommand(command="pokebanco", description="Ver suas pokecoins e pokebolas"),
        BotCommand(command="capturar", description="Capturar um card"),
        BotCommand(command="pokebola", description="Exibir informações sobre um card"),
        BotCommand(command="pokemart", description="Acessar o Pokémart"),
        BotCommand(command="pokedex", description="Ver todas as coleções"),
        BotCommand(command="comprarbolas", description="Comprar Pokébolas"),
        BotCommand(command="doarcards", description="Doar cards para outro treinador"),
        BotCommand(command="doarbolas", description="Doar pokebolas para outro treinador"),
        BotCommand(command="doarcoins", description="Doar pokecoins para outro treinador"),
        BotCommand(command="venderc", description="Vender cards para o Pokemart"),
        BotCommand(command="roubar", description="Trocar cartas com outro treinador"),
        BotCommand(command="favpoke", description="Definir seu card favorito"),
        BotCommand(command="ginasio", description="Ver o ranking do ginásio"),
    ]
    await bot.set_my_commands(commands)

    # Admin-specific commands
    admin_commands = [
        BotCommand(command="addcarta", description="(Admin) Adicionar uma nova carta"),
        BotCommand(command="imgpd", description="(Admin) Adicionar imagem a um grupo"),
        BotCommand(command="rclicar", description="(Admin) Distribuir pokebolas"),
        BotCommand(command="rcoins", description="(Admin) Distribuir pokecoins"),
        BotCommand(command="start", description="Iniciar o bot"),
        BotCommand(command="help", description="Obter ajuda sobre os comandos"),
        BotCommand(command="jornada", description="Registrar-se no bot"),
        BotCommand(command="mochila", description="Ver sua mochila"),
        BotCommand(command="pokebanco", description="Ver suas pokecoins e pokebolas"),
        BotCommand(command="capturar", description="Capturar um card"),
        BotCommand(command="pokebola", description="Exibir informações sobre um card"),
        BotCommand(command="pokemart", description="Acessar o Pokémart"),
        BotCommand(command="pokedex", description="Ver todas as coleções"),
        BotCommand(command="comprarbolas", description="Comprar Pokébolas"),
        BotCommand(command="doarcards", description="Doar cards para outro treinador"),
        BotCommand(command="doarbolas", description="Doar pokebolas para outro treinador"),
        BotCommand(command="doarcoins", description="Doar pokecoins para outro treinador"),
        BotCommand(command="venderc", description="Vender cards para o Pokemart"),
        BotCommand(command="roubar", description="Trocar cartas com outro treinador"),
        BotCommand(command="favpoke", description="Definir seu card favorito"),
        BotCommand(command="ginasio", description="Ver o ranking do ginásio"),
    ]

    # Fetch the list of admin users from the database
    async with get_session() as session:
        result = await session.execute(select(User).where(User.is_admin == 1))
        admin_users = result.scalars().all()

    # Assign admin commands to each admin user
    for admin in admin_users:
        try:
            await bot.set_my_commands(admin_commands, scope={"type": "chat", "chat_id": admin.id})
            logging.info(f"Admin commands set for user {admin.id} (@{admin.username})")
        except Exception as e:
            logging.error(f"Failed to set admin commands for user {admin.id}: {e}")

# Run the bot
async def main():
    # Comment this if you want to reset the database schema
    await create_db()

    # Recreate the database schema. Uncomment this if you want to reset the database schema
    # await recreate_database()

    # Set bot commands
    await set_bot_commands(bot)

    # Start polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())