from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

# Database imports
from database.session import get_session
from database.crud_user import get_user_by_id
from database.crud_user import get_user_inventory  # Import the inventory query

router = Router()

@router.message(Command("mochila"))
async def mochila_command(message: Message):
    user_id = message.from_user.id

    async with get_session() as session:
        user = await get_user_by_id(session, user_id)

        if not user:
            await message.answer("Você ainda não está registrado. Use /jornada para começar!")
            return

        # Query the user's inventory
        inventory = await get_user_inventory(session, user_id)  # Replace with actual query
        if not inventory:
            await message.answer("Sua mochila está vazia! Capture algumas cartas usando /cap.")
        else:
            inventory_text = "\n".join([f"- {card.name}" for card in inventory])
            await message.answer(f"Sua mochila contém:\n{inventory_text}")