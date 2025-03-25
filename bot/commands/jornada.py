"""
This module handles the /jornada command using an interactive flow (via FSM).
Users are asked to choose a nickname. If it's available, they confirm via inline
buttons. The first user who registers is automatically assigned as admin.

Key points:
- Only one /jornada flow. We do not process /jornada <nickname> directly.
- If user is already registered, they are informed.
- If user is the very first in the database, is_admin = 1; otherwise 0.
"""

import asyncio
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError

from database.session import get_session
from database.models import User
from database.crud_user import get_user_by_id, get_user_by_nickname

router = Router()

class JornadaStates(StatesGroup):
    """
    Defines the finite states for the /jornada command flow.
    """
    waiting_for_nickname = State()
    confirming_nickname = State()


@router.message(Command("jornada"))
async def jornada_command(message: Message, state: FSMContext):
    """
    Entry point for /jornada command.
    1. Check if user is already registered.
    2. If registered, notify; else prompt for a nickname.
    """
    user_id = message.from_user.id
    username = message.from_user.username or "Usuário sem @"

    async with get_session() as session:
        # Check if the user is already registered in the DB
        user = await get_user_by_id(session, user_id)

    if user:
        await message.answer(
            f"Você já está registrado como @{user.nickname}, {username}! 🚀",
            parse_mode=ParseMode.HTML
        )
    else:
        await message.answer(
            "Bem-vindo à sua jornada! 🎉\n"
            "Por favor, escolha um @ único para o bot te chamar (sem espaços e "
            "com até 20 caracteres):",
            parse_mode=ParseMode.HTML
        )
        # Move to the next FSM state
        await state.set_state(JornadaStates.waiting_for_nickname)


@router.message(JornadaStates.waiting_for_nickname)
async def process_nickname(message: Message, state: FSMContext):
    """
    Called once the user types a nickname after /jornada.
    Validates nickname length, no spaces, and availability.
    """
    nickname = message.text.strip()

    # Basic validations
    if len(nickname) > 20:
        await message.answer(
            "O @ deve ter no máximo 20 caracteres. Tente novamente:",
            parse_mode=ParseMode.HTML
        )
        return
    if " " in nickname:
        await message.answer(
            "O @ não pode conter espaços. Tente novamente:",
            parse_mode=ParseMode.HTML
        )
        return

    # Check if this nickname is already taken
    async with get_session() as session:
        existing = await get_user_by_nickname(session, nickname)
        if existing:
            await message.answer(
                "Este @ já está em uso. Escolha outro:",
                parse_mode=ParseMode.HTML
            )
            return

    # Temporarily store the nickname in FSM context
    await state.update_data(nickname=nickname)

    # Prepare inline keyboard for user confirmation
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Sim", callback_data="confirm_nickname")
    keyboard.button(text="Não", callback_data="reject_nickname")

    await message.answer(
        f"O seu nickname será @{nickname}. Você deseja confirmar?",
        reply_markup=keyboard.as_markup(),
        parse_mode=ParseMode.HTML
    )
    # Transition to confirmation state
    await state.set_state(JornadaStates.confirming_nickname)


@router.callback_query(
    F.data.in_({"confirm_nickname", "reject_nickname"}),
    JornadaStates.confirming_nickname
)
async def handle_confirmation(callback: CallbackQuery, state: FSMContext):
    """
    Handles inline button taps:
    - 'confirm_nickname': create the user in the database.
      If it's the first user, they become admin.
    - 'reject_nickname': ask user to re-enter nickname.
    """
    user_id = callback.from_user.id
    username = callback.from_user.username or "Usuário sem @"
    data = await state.get_data()
    nickname = data.get("nickname")

    if callback.data == "confirm_nickname":
        async with get_session() as session:
            try:
                # Count how many users exist
                result = await session.execute(select(func.count(User.id)))
                user_count = result.scalar_one_or_none() or 0
                is_first_user = (user_count == 0)

                # Create the new user
                new_user = User(
                    id=user_id,
                    username=username,
                    nickname=nickname,
                    is_admin=1 if is_first_user else 0
                )
                session.add(new_user)
                await session.commit()

                # Clear the FSM state
                await state.clear()

                # Send success message
                if is_first_user:
                    await callback.message.edit_text(
                        f"Parabéns, @{nickname}! Você é o(a) primeiro(a) usuário(a) "
                        "e agora é um administrador! 🎉",
                        parse_mode=ParseMode.HTML
                    )
                else:
                    await callback.message.edit_text(
                        f"Parabéns, @{nickname}! Você agora está registrado e pronto "
                        "para capturar cartas! 🎉",
                        parse_mode=ParseMode.HTML
                    )

            except IntegrityError:
                await session.rollback()
                await callback.message.edit_text(
                    "Houve um erro ao salvar seu @. Por favor, tente novamente.",
                    parse_mode=ParseMode.HTML
                )

    else:  # reject_nickname
        await callback.message.edit_text(
            "Por favor, escolha outro @ único para o bot te chamar "
            "(sem espaços e com até 20 caracteres):",
            parse_mode=ParseMode.HTML
        )
        # Move back to waiting_for_nickname
        await state.set_state(JornadaStates.waiting_for_nickname)
