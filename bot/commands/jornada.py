from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Simulating a database with dictionaries (replace with actual database logic later)
registered_users = {}  # Key: Telegram ID, Value: {"username": str, "nickname": str, "cards": [], "coins": int}
nicknames = set()  # Set to track all registered nicknames

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

    if user_id in registered_users:
        nickname = registered_users[user_id]["nickname"]
        await message.answer(f"Você já está registrado como @{nickname}, {username}! 🚀")
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
    if nickname in nicknames:
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
    data = await state.get_data()
    nickname = data.get("nickname")

    if callback.data == "confirm_nickname":
        # Save the user and nickname
        username = callback.from_user.username or "Usuário sem @"
        registered_users[user_id] = {"username": username, "nickname": nickname, "cards": [], "coins": 0}
        nicknames.add(nickname)

        # Clear the state
        await state.clear()

        await callback.message.edit_text(
            f"Parabéns, @{nickname}! Você agora está registrado no bot e pronto para capturar cartas! 🎉"
        )
    elif callback.data == "reject_nickname":
        # Ask the user to choose another nickname
        await callback.message.edit_text(
            "Por favor, escolha outro @ único para o bot te chamar (sem espaços e com até 20 caracteres):"
        )
        # Set the state back to "waiting_for_nickname"
        await state.set_state(JornadaStates.waiting_for_nickname)