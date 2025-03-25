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

# Define FSM states
class AdminFSM(StatesGroup):
    waiting_for_password = State()

@router.message(Command(commands=["admin"]))
async def start_admin_promotion(message: types.Message, state: FSMContext):
    # Ensure the command includes a nickname
    if len(message.text.split()) != 2:
        await message.reply("❗ **Erro:** Use o comando no formato `/admin @nickname`.", parse_mode=ParseMode.MARKDOWN)
        return

    nickname = message.text.split()[1].lstrip("@")

    # Check if the user exists in the database
    async with get_session() as session:
        result = await session.execute(select(User).where(User.nickname == nickname))
        user = result.scalar_one_or_none()

        if not user:
            await message.reply(f"❌ **Erro:** O usuário com o nickname @{nickname} não foi encontrado.")
            return

    # Save the nickname in the FSM context and ask for the password
    await state.update_data(nickname=nickname)
    await message.reply("🔒 **Digite a senha de administrador para continuar:**", parse_mode=ParseMode.MARKDOWN)
    await state.set_state(AdminFSM.waiting_for_password)

@router.message(AdminFSM.waiting_for_password)
async def process_admin_password(message: types.Message, state: FSMContext):
    # Retrieve the nickname from the FSM context
    data = await state.get_data()
    nickname = data.get("nickname")

    # Check if the password is correct
    if message.text != ADMIN_PASSWORD:
        await message.reply("❌ **Senha incorreta!** A promoção foi cancelada.", parse_mode=ParseMode.MARKDOWN)
        await state.clear()
        return

    # Promote the user to admin
    async with get_session() as session:
        result = await session.execute(select(User).where(User.nickname == nickname))
        user = result.scalar_one_or_none()

        if user:
            user.is_admin = 1
            await session.commit()
            await message.reply(f"✅ **Sucesso!** O usuário @{nickname} agora é um administrador.", parse_mode=ParseMode.MARKDOWN)
        else:
            await message.reply(f"❌ **Erro:** O usuário @{nickname} não foi encontrado no banco de dados.")

    # Clear the FSM state
    await state.clear()