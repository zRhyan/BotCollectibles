from aiogram import Router, types
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from database.models import User, Card, Inventory
from database.session import async_session

router = Router()

@router.message(Command(commands=["cap", "capturar"]))
async def capturar_card(message: types.Message):
    user_id = message.from_user.id

    async with async_session() as session:
        # Check if user exists
        user = await session.get(User, user_id)
        if not user:
            await message.reply("Você precisa se registrar primeiro usando o comando /jornada.")
            return

        # Check if user has pokéballs
        if user.pokeballs <= 0:
            await message.reply("Você não tem pokébolas suficientes para capturar um card!")
            return

        # Deduct one pokéball
        user.pokeballs -= 1

        # Select a random card
        result = await session.execute(select(Card).order_by(func.random()).limit(1))
        card = result.scalar_one_or_none()

        if not card:
            await message.reply("Nenhum card disponível para captura no momento.")
            return

        # Add card to user's inventory
        inventory_item = await session.execute(
            select(Inventory).where(Inventory.user_id == user_id, Inventory.card_id == card.id)
        )
        inventory_item = inventory_item.scalar_one_or_none()

        if inventory_item:
            inventory_item.quantity += 1
        else:
            new_inventory = Inventory(user_id=user_id, card_id=card.id, quantity=1)
            session.add(new_inventory)

        await session.commit()

        # Reply with success message
        await message.reply(f"Parabéns! Você capturou o card: {card.name} 🎉")