import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message
from aiogram.filters import Command
from dotenv import load_dotenv
import os

#Command import
from commands.help import help_command
from commands.start import start_command

# Carregar variáveis do .env
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Configuração do bot
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Logger (para depuração)
logging.basicConfig(level=logging.INFO)

# Dispatcher command registration
dp.message.register(start_command, Command("start"))
dp.message.register(help_command, Command("help"))

# Executar o bot
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())