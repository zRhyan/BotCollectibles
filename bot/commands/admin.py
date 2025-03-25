from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.enums import ParseMode
from sqlalchemy.future import select
from database.models import User
from database.session import get_session
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

router = Router()

@router.message(Command(commands=["admin"]))
async def promote_to_admin(message: types.Message):
    # Ensure the command includes a nickname
    if len(message.text.split()) != 2:
        await message.reply("❗ **Erro:** Use o comando no formato `/admin @nickname`.")
        return

    nickname = message.text.split()[1].lstrip("@")

    # Check if the user issuing the command is an admin
    async with get_session() as session:
        result = await session.execute(select(User).where(User.id == message.from_user.id))
        current_user = result.scalar_one_or_none()

        if not current_user or current_user.is_admin == 0:
            await message.reply("🚫 **Acesso negado!** Somente administradores podem usar este comando.")
            return

        # Check if the target user exists
        result = await session.execute(select(User).where(User.nickname == nickname))
        target_user = result.scalar_one_or_none()

        if not target_user:
            await message.reply(f"❌ **Erro:** O usuário com o nickname @{nickname} não foi encontrado.")
            return

        # Promote the target user to admin
        target_user.is_admin = 1
        await session.commit()

        await message.reply(f"✅ **Sucesso!** O usuário @{nickname} agora é um administrador.")