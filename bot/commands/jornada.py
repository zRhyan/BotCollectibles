import os
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
import logging

from database.session import get_session
from database.models import User
from database.crud_user import get_user_by_id, get_user_by_nickname

router = Router()

# Define a list of admin usernames (can also be loaded from environment variables)
PREDEFINED_ADMINS = os.getenv("PREDEFINED_ADMINS", "").split(",")  # Comma-separated list of usernames


class JornadaStates(StatesGroup):
    waiting_for_nickname = State()
    confirming_nickname = State()


@router.message(Command("jornada"))
async def jornada_command(message: Message, state: FSMContext):
    logging.info(f"Received /jornada command from user {message.from_user.id} (@{message.from_user.username})")

    try:
        await message.answer("The /jornada command is working!")
    except Exception as e:
        logging.error(f"Error in /jornada command: {e}")


@router.callback_query(
    F.data.in_({"confirm_nickname", "reject_nickname"}),
    JornadaStates.confirming_nickname
)
async def handle_confirmation(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    username = callback.from_user.username or "Usuário sem @"
    data = await state.get_data()
    nickname = data.get("nickname")

    if callback.data == "confirm_nickname":
        async with get_session() as session:
            try:
                # Check if the user is in the predefined admin list
                is_predefined_admin = username in PREDEFINED_ADMINS

                # Determine if the user should be an admin
                is_admin = 1 if is_predefined_admin else 0

                # Create the new user
                new_user = User(
                    id=user_id,
                    username=username,
                    nickname=nickname,
                    is_admin=is_admin,
                    pokeballs=3  # Set initial pokeballs to 3
                )
                session.add(new_user)
                await session.commit()

                # Clear the FSM state
                await state.clear()

                # Send success message
                if is_admin:
                    await callback.message.edit_text(
                        f"Parabéns, @{nickname}! Você agora é um administrador! 🎉",
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