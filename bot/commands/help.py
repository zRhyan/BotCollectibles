from aiogram import types
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.enums import ParseMode

async def help_command(message: Message):
    help_text = (
        "📜 **Bem-vindo, Treinador! Aqui estão os comandos disponíveis:** 📜\n\n"
        "🌟 **Comandos Básicos:**\n"
        "🔹 `/start` - Comece sua jornada Pokémon! 🎮\n"
        "🔹 `/help` - Veja esta mensagem de ajuda. 🆘\n\n"
        "🎒 **Comandos de Jogo:**\n"
        "🔹 `/jornada` - Inscreva-se e torne-se um treinador Pokémon! 🚀\n"
        "🔹 `/mochila` - Confira os itens que você carrega. 🎒\n"
        "🔹 `/pokebanco` - Veja suas riquezas no PokéBanco. 🏦\n\n"
        "⚔️ **Comandos de Captura:**\n"
        "🔹 `/capturar` ou `/cap` - Tente capturar um card raro! 🎯\n\n"
        "Divirta-se e boa sorte na sua aventura! ⚡"
    )
    await message.answer(help_text, parse_mode=ParseMode.MARKDOWN)