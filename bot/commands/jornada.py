from aiogram import Router, F, types
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
from sqlalchemy.exc import IntegrityError
from sqlalchemy.future import select
from sqlalchemy.sql import func

from database.session import get_session
from database.crud_user import get_user_by_id, get_user_by_nickname, create_user
from database.models import User

# Define a Router
router = Router()

# Define FSM States
class JornadaStates(StatesGroup):
    waiting_for_nickname = State()
    confirming_nickname = State()

# Command Handler for /jornada
@router.message(Command("jornada"))
async def jornada_command(message: Message, state: FSMContext):
    user_id = message.from_user.id
    username = message.from_user.username or "Usuário sem @"

    async with get_session() as session:
        # Check if the user is already registered
        user = await get_user_by_id(session, user_id)

    if user:
        await message.answer(f"Você já está registrado como @{user.nickname}, {username}! 🚀")
    else:
        await message.answer(
            "Bem-vindo à sua jornada! 🎉\n"
            "Por favor, escolha um @ único para o bot te chamar (sem espaços e com até 20 caracteres):"
        )
        # Set the state to "waiting_for_nickname"
        await state.set_state(JornadaStates.waiting_for_nickname)

# Handler to Process Nickname Input
@router.message(JornadaStates.waiting_for_nickname)
async def process_nickname(message: Message, state: FSMContext):
    user_id = message.from_user.id
    nickname = message.text.strip()

    # Validate nickname
    if len(nickname) > 20:
        await message.answer("O @ deve ter no máximo 20 caracteres. Tente novamente:")
        return
    if " " in nickname:
        await message.answer("O @ não pode conter espaços. Tente novamente:")
        return

    async with get_session() as session:
        # Check if the nickname is already taken
        existing_nickname = await get_user_by_nickname(session, nickname)

        if existing_nickname:
            await message.answer("Este @ já está em uso. Escolha outro:")
            return

    # Save the nickname temporarily in FSM context
    await state.update_data(nickname=nickname)

    # Create confirmation buttons
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Sim", callback_data="confirm_nickname")
    keyboard.button(text="Não", callback_data="reject_nickname")
    keyboard = keyboard.as_markup()

    # Ask for confirmation
    await message.answer(
        f"O seu nickname será @{nickname}. Você deseja confirmar?",
        reply_markup=keyboard
    )

    # Set the state to "confirming_nickname"
    await state.set_state(JornadaStates.confirming_nickname)

# Handler for Confirmation Buttons
@router.callback_query(F.data.in_({"confirm_nickname", "reject_nickname"}), JornadaStates.confirming_nickname)
async def handle_confirmation(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    username = callback.from_user.username or "Usuário sem @"
    data = await state.get_data()
    nickname = data.get("nickname")

    if callback.data == "confirm_nickname":
        async with get_session() as session:
            try:
                # Save the user to the database
                new_user = await create_user(session, user_id, username, nickname)

                # Clear the state
                await state.clear()

                await callback.message.edit_text(
                    f"Parabéns, @{nickname}! Você agora está registrado no bot e pronto para capturar cartas! 🎉"
                )
            except IntegrityError:
                await session.rollback()
                await callback.message.edit_text(
                    "Houve um erro ao salvar seu @. Por favor, tente novamente."
                )
    elif callback.data == "reject_nickname":
        # Ask the user to choose another nickname
        await callback.message.edit_text(
            "Por favor, escolha outro @ único para o bot te chamar (sem espaços e com até 20 caracteres):"
        )
        # Set the state back to "waiting_for_nickname"
        await state.set_state(JornadaStates.waiting_for_nickname)

@router.message(Command(commands=["jornada"]))
async def register_user(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    nickname = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else None

    if not nickname:
        await message.reply(
            "❗ **Erro:** Você precisa fornecer um nickname. Use o comando no formato `/jornada <nickname>`.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    async with get_session() as session:
        # Check if the user is already registered
        existing_user = await session.execute(select(User).where(User.id == user_id))
        if existing_user.scalar_one_or_none():
            await message.reply("❌ Você já está registrado no bot!")
            return

        # Check if this is the first user
        result = await session.execute(select(func.count(User.id)))
        user_count = result.scalar_one_or_none()  # Get the count of users
        is_first_user = user_count == 0  # True if no users exist

        print(f"User count: {user_count}")
        print(f"Is first user: {is_first_user}")

        # Register the user
        new_user = User(
            id=user_id,
            username=username,
            nickname=nickname,
            is_admin=1 if is_first_user else 0  # First user becomes admin
        )
        session.add(new_user)
        await session.commit()

        if is_first_user:
            await message.reply(
                f"🎉 Bem-vindo, {nickname}! Você foi registrado como o primeiro usuário e agora é um administrador!"
            )
        else:
            await message.reply(f"🎉 Bem-vindo, {nickname}! Sua jornada começou!")