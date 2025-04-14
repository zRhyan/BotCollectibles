from aiogram import types
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.enums import ParseMode

async def start_command(message: Message):
    user_name = message.from_user.first_name or "Treinador"
    welcome_message = (
        f"🎑 *Seja bem-vindo, {user_name}!*\n\n"
        "Se você deseja ser um treinador informado e cheio de vantagens, entre no nosso "
        "[Instituto de Informações de Pokedéx](https://t.me/pokunews). Somente assim você poderá usar os comandos necessários "
        "para conseguir seus amados pokémons!\n\n"
        "🏆 *Que sua aventura seja sábia e seu lugar no Ginásio seja garantido!* E lembre-se: nosso Poku está esperando por você!!"
    )
    await message.answer(welcome_message, parse_mode=ParseMode.MARKDOWN)