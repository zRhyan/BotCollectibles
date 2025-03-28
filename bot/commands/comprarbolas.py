from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from sqlalchemy.future import select
from sqlalchemy import update
from database.models import User
from database.session import get_session

router = Router()

@router.message(Command("comprarbolas"))
async def comprarbolas_command(message: types.Message):
    """
    Handles the /comprarbolas command to allow users to purchase Pokébolas.
    Usage:
    - /comprarbolas quantidade
    """
    user_id = message.from_user.id

    # Parse the command arguments
    text_parts = message.text.split(maxsplit=1)
    if len(text_parts) < 2:
        async with get_session() as session:
            # Fetch the user from the database
            result = await session.execute(select(User).where(User.id == message.from_user.id))
            user = result.scalar_one_or_none()

            if not user:
                await message.reply(
                    "❌ **Erro:** Você ainda não está registrado no sistema. Use o comando `/jornada` para começar sua aventura.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

            await message.reply(
                "❗ **Erro:** Você precisa fornecer a quantidade de Pokébolas que deseja comprar.\n\n"
                "💡 **Exemplo de uso:**\n"
                "`/comprarbolas 10`\n\n"
                "🎯 **Detalhes:**\n"
                "Cada Pokébola custa **1250 pokecoins**.\n\n"
                f"💰 **Suas pokecoins:** {user.coins}\n"
                f"🎯 **Suas Pokébolas:** {user.pokeballs}",
                parse_mode=ParseMode.MARKDOWN
            )
        return

    try:
        quantity = int(text_parts[1])
        if quantity <= 0:
            raise ValueError("A quantidade deve ser maior que zero.")
    except ValueError:
        await message.reply(
            "❗ **Erro:** A quantidade deve ser um número inteiro válido maior que zero.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Define the cost of Pokébolas
    cost_per_pokebola = 1250  # Example: 5 coins per Pokébola
    total_cost = quantity * cost_per_pokebola

    async with get_session() as session:
        # Fetch the user from the database
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            await message.reply(
                "❌ **Erro:** Você ainda não está registrado no sistema. Use o comando `/jornada` para começar sua aventura.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Check if the user has enough coins
        if user.coins < total_cost:
            await message.reply(
                f"❌ **Erro:** Você não tem pokecoins suficientes para comprar {quantity} Pokébolas.\n"
                f"💰 **Suas pokecoins:** {user.coins}\n"
                f"💵 **Custo total:** {total_cost} pokecoins",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Deduct coins and add Pokébolas
        user.coins -= total_cost
        user.pokeballs += quantity
        await session.commit()

    # Confirm the purchase
    await message.reply(
        f"✅ **Sucesso!** Você comprou {quantity} Pokébolas por {total_cost} pokecoins.\n"
        f"💰 **Pokecoins restantes:** {user.coins}\n"
        f"🎯 **Pokébolas totais:** {user.pokeballs}",
        parse_mode=ParseMode.MARKDOWN
    )