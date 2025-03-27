from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.enums import ParseMode
from sqlalchemy.orm import joinedload
from sqlalchemy import select

# Database imports
from database.session import get_session
from database.models import User

router = Router()

@router.message(Command("pokebanco"))
async def pokebanco_command(message: Message):
    """
    Handles the /pokebanco command to display the user's bank information.
    """
    user_id = message.from_user.id

    async with get_session() as session:
        # Query the user with eager loading of the inventory relationship
        result = await session.execute(
            select(User)
            .options(joinedload(User.inventory))  # Eagerly load the inventory relationship
            .where(User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            await message.answer(
                "❌ **Treinador não encontrado!** ❌\n\n"
                "Parece que você ainda não começou sua jornada. Use `/jornada` para se registrar e começar sua aventura! 🚀",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Retrieve user data
        coins = user.coins
        pokeballs = user.pokeballs
        captures = user.captures  # Dynamically calculated from the inventory

        # Send the response to the user
        await message.answer(
            f"🏦 **Bem-vindo ao PokéBanco!** 🏦\n\n"
            f"💰 **Moedas:** `{coins}`\n"
            f"🎯 **Pokébolas:** `{pokeballs}`\n"
            f"📸 **Capturas:** `{captures}`\n\n"
            f"Continue sua jornada e acumule mais riquezas e conquistas! 🌟",
            parse_mode=ParseMode.MARKDOWN
        )