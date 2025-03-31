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
        "🔹 `/pokebanco` - Veja suas riquezas no PokéBanco. 🏦\n"
        "🔹 `/pokefav` - Favorite um card e um emoji! 💌"
        "🔹 `/ginasio` cardid - Veja o ranking do ginásio para um card específico. 🏆\n"
        "🔹 `/pokedex` ou `/pd`- Veja todas as coleções. 🗂\n"
        "🔹 `/pokebola` ou `/pb` cardid ou cardname - Visualize informações sobre um card. 🃏\n\n"
        "⚔️ **Comandos de Captura:**\n"
        "🔹 `/capturar` ou `/cap` - Tente capturar um card raro! 🎯\n"
        "🔹 `/roubar` - Troque cartas com outro treinador. Use o formato:\n"
        "   `/roubar id1 xqty1, id2 xqty2 X id3 xqty3, id4 xqty4` (responda à mensagem do outro treinador). 🔄\n\n"
        "🛒 **Comandos de Loja:**\n"
        "🔹 `/pokemart` ou `/pokem` - Acesse o Pokémart para comprar cards especiais e capturas. 🛍️\n"
        "🔹 `/comprarbolas quantidade` - Compre Pokébolas para capturar mais cards. 🎯\n"
        "🔹 `/doarcards` - Doe cards para outros treinadores. 🎁\n"
        "🔹 `/doarbolas` - Doe Pokebolas para outros treinadores. 🎁\n"
        "🔹 `/doarcoins` - Doe Pokecoins para outros treinadores. 🎁\n"
        "🔹 `/venderc` - Venda seus cards para o Pokemart. 💰\n\n"
        "Divirta-se e boa sorte na sua aventura! ⚡"
    )
    await message.answer(help_text, parse_mode=ParseMode.MARKDOWN)