from aiogram import types
from aiogram.filters import Command
from aiogram.types import Message

async def help_command(message: Message):
    help_text = (
        "Os seguintes comandos estão disponíveis:\n"
        "/start - Iniciar o bot\n"
        "/help - Mostrar esta mensagem de ajuda\n"
        "/jornada - Inscrever-se no bot\n"
        "/mochila - Mostrar seu inventário\n"
    )
    await message.answer(help_text)