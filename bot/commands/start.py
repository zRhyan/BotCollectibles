from aiogram import types
from aiogram.filters import Command
from aiogram.types import Message

async def start_command(message: Message):
    await message.answer("Olá! Seu bot está funcionando! 🚀")