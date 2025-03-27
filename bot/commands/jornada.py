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
    user_id = message.from_user.id
    username = message.from_user.username or "Usuário sem @"

    # Access the bot instance from the message object
    bot = message.bot

    # Check if the user is a member of @pokunews
    try:
        member = await bot.get_chat_member("@pokunews", user_id)
        if member.status not in ["member", "administrator", "creator"]:
            await message.answer(
                "⚠️ Você precisa ser membro do [Instituto de Informações de Pokedéx](https://t.me/pokunews) "
                "para se registrar no bot. Por favor, entre no canal e tente novamente.",
                parse_mode="Markdown"
            )
            return
    except Exception:
        await message.answer(
            "⚠️ Não foi possível verificar sua associação ao [Instituto de Informações de Pokedéx](https://t.me/pokunews). "
            "Por favor, entre no canal e tente novamente.",
            parse_mode="Markdown"
        )
        return

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
    nickname = message.text.strip()

    # Validação básica
    if len(nickname) > 20:
        await message.answer(
            "⚠️ O @ deve ter no máximo 20 caracteres. Tente novamente:",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    if " " in nickname:
        await message.answer(
            "⚠️ O @ não pode conter espaços. Tente novamente:",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Verifica se o apelido já está em uso
    async with get_session() as session:
        existing = await get_user_by_nickname(session, nickname)
        if existing:
            await message.answer(
                "⚠️ Este @ já está em uso. Escolha outro:",
                parse_mode=ParseMode.MARKDOWN
            )
            return

    # Armazena temporariamente no contexto FSM
    await state.update_data(nickname=nickname)

    # Teclado inline de confirmação
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Sim", callback_data="confirm_nickname")
    keyboard.button(text="Não", callback_data="reject_nickname")
    keyboard.adjust(2)

    await message.answer(
        f"O seu nickname será @{nickname}. Você deseja confirmar?",
        reply_markup=keyboard.as_markup(),
        parse_mode=ParseMode.MARKDOWN
    )

    # Avança para o próximo estado
    await state.set_state(JornadaStates.confirming_nickname)



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