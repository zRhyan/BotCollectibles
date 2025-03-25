from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.enums import ParseMode

# Database imports
from database.session import get_session
from database.crud_user import get_user_by_id

router = Router()

@router.message(Command("pokebanco"))
async def pokebanco_command(message: Message):
    user_id = message.from_user.id

    async with get_session() as session:
        # Query the user from the database
        user = await get_user_by_id(session, user_id)

        if not user:
            await message.answer(
                "❌ **Treinador não encontrado!** ❌\n\n"
                "Parece que você ainda não começou sua jornada. Use `/jornada` para se registrar e começar sua aventura! 🚀",
                 parse_mode=ParseMode.MARKDOWN
            )
            return

        # Retrieve user data
        coins = user.coins
        pokeballs = getattr(user, "pokeballs", 0)  # Default to 0 if not present
        captures = getattr(user, "captures", 0)  # Default to 0 if not present

        # Send the response to the user
        await message.answer(
            f"🏦 **Bem-vindo ao PokéBanco!** 🏦\n\n"
            f"💰 **Moedas:** `{coins}`\n"
            f"🎯 **Pokébolas:** `{pokeballs}`\n"
            f"📸 **Capturas:** `{captures}`\n\n"
            f"Continue sua jornada e acumule mais riquezas e conquistas! 🌟",
            parse_mode=ParseMode.MARKDOWN
        )