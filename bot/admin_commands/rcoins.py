import os
from dotenv import load_dotenv
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from sqlalchemy.future import select
from sqlalchemy import update
from database.models import User
from database.session import get_session

# Load environment variables
load_dotenv()

ALLOWED_USERNAMES = os.getenv("ALLOWED_USERNAMES", "").split(",")  # Comma-separated list of allowed Telegram usernames

router = Router()

@router.message(Command("rcoins"))
async def distribute_coins_command(message: types.Message):
    """
    Admin command to distribute coins.
    Usage:
    - /rcoins quantidade (distributes to all users)
    - /rcoins nickname quantidade (distributes to a specific user)
    """
    # Check if the user is allowed
    if message.from_user.username not in ALLOWED_USERNAMES:
        await message.reply(
            "🚫 **Acesso negado!** Você não tem permissão para usar este comando.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Check if the user is an admin
    async with get_session() as session:
        result = await session.execute(select(User).where(User.id == message.from_user.id))
        admin_user = result.scalar_one_or_none()

        if not admin_user or admin_user.is_admin == 0:
            await message.reply(
                "🚫 **Acesso negado!** Somente administradores podem usar este comando.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

    # Parse the command arguments
    text_parts = message.text.split(maxsplit=2)
    if len(text_parts) < 2:
        await message.reply(
            "❗ **Erro:** Você precisa fornecer a quantidade ou o nickname e a quantidade.\n"
            "Exemplo:\n"
            "`/rcoins 100` (para todos os usuários)\n"
            "`/rcoins nickname 100` (para um usuário específico)",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Handle the case for all users
    if len(text_parts) == 2:
        try:
            quantity = int(text_parts[1])
        except ValueError:
            await message.reply(
                "❗ **Erro:** A quantidade deve ser um número inteiro válido.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Update coins for all users
        async with get_session() as session:
            await session.execute(
                update(User).values(coins=User.coins + quantity)
            )
            await session.commit()

        await message.reply(
            f"✅ **Sucesso!** {quantity} pokecoins foram distribuídas para todos os usuários.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Handle the case for a specific user
    if len(text_parts) == 3:
        nickname = text_parts[1].strip()
        try:
            quantity = int(text_parts[2])
        except ValueError:
            await message.reply(
                "❗ **Erro:** A quantidade deve ser um número inteiro válido.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Update coins for the specific user
        async with get_session() as session:
            result = await session.execute(select(User).where(User.nickname == nickname))
            user = result.scalar_one_or_none()

            if not user:
                await message.reply(
                    f"❌ **Erro:** Nenhum usuário encontrado com o nickname `{nickname}`.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

            user.coins += quantity
            await session.commit()

        await message.reply(
            f"✅ **Sucesso!** {quantity} pokecoins foram adicionadas ao usuário `{nickname}`.",
            parse_mode=ParseMode.MARKDOWN
        )