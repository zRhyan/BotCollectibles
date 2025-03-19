import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message
from aiogram.filters import Command
from dotenv import load_dotenv
import os

# Carregar variáveis do .env
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Configuração do bot
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Logger (para depuração)
logging.basicConfig(level=logging.INFO)

# Comando de teste
@dp.message(Command("start"))
async def start_command(message: Message):
    await message.answer("Olá! Seu bot está funcionando! 🚀")

# Executar o bot
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
