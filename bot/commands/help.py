from aiogram import types
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.enums import ParseMode

async def help_command(message: Message):
    help_text = (
        "📜 **Comandos Disponíveis** 📜\n\n"
        "🔹 `/start` - Iniciar o bot\n"
        "🔹 `/help` - Mostrar esta mensagem de ajuda\n"
        "🔹 `/jornada` - Inscrever-se no bot\n"
        "🔹 `/mochila` - Mostrar seu inventário\n"
        "🔹 `/pokebanco` - Ver o estado do seu PokéBanco\n"
    )
    await message.answer(help_text, parse_mode=ParseMode.MARKDOWN)