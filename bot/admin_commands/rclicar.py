from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from sqlalchemy.future import select
from database.models import User
from database.session import get_session

router = Router()

@router.message(Command("rclicar"))
async def reset_pokeballs_command(message: types.Message):
    """
    Admin command to reset a user's Pokéballs to 10.
    Usage: /rclicar <nickname>
    """
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
    text_parts = message.text.split(maxsplit=1)
    if len(text_parts) < 2:
        await message.reply(
            "❗ **Erro:** Você precisa fornecer o nickname do usuário.\n"
            "Exemplo: `/rclicar nickname`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    nickname = text_parts[1].strip()

    # Reset the user's Pokéballs
    async with get_session() as session:
        result = await session.execute(select(User).where(User.nickname == nickname))
        user = result.scalar_one_or_none()

        if not user:
            await message.reply(
                f"❌ **Erro:** Nenhum usuário encontrado com o nickname `{nickname}`.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Reset Pokéballs to 10
        user.pokeballs = 10
        await session.commit()

        await message.reply(
            f"✅ **Sucesso!** As Pokébolas do usuário `{nickname}` foram resetadas para 10.",
            parse_mode=ParseMode.MARKDOWN
        )