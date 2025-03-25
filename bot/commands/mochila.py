from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

# Database imports
from database.session import get_session
from database.crud_user import get_user_by_id
from database.crud_user import get_user_inventory  # Import the inventory query

from aiogram.enums import ParseMode  # For markdown

router = Router()

@router.message(Command("mochila"))
async def mochila_command(message: Message):
    user_id = message.from_user.id

    async with get_session() as session:
        user = await get_user_by_id(session, user_id)

        if not user:
            await message.answer(
                "🚫 **Você ainda não é um treinador registrado!**\n"
                "Use o comando /jornada para iniciar sua aventura e começar a capturar criaturas lendárias! 🌟",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Query the user's inventory
        inventory = await get_user_inventory(session, user_id)

        if not inventory:
            await message.answer(
                "🎒 **Sua Mochila está vazia!**\n"
                "Você ainda não capturou nenhum card...\n\n"
                "Use o comando /cap para lançar uma pokébola e tentar a sorte! 🍀",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            # Adjust the list comprehension based on the structure of inventory
            inventory_text = "\n".join(
                [f"🃏 **{item.card.name}** ×{item.quantity}" for item in inventory]
            )

            await message.answer(
                f"🎒 **Mochila do Treinador**\n"
                f"Você possui os seguintes cards:\n\n"
                f"{inventory_text}\n\n"
                f"Continue explorando e completando sua coleção! ✨",
                parse_mode=ParseMode.MARKDOWN
            )
