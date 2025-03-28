from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.future import select
from database.session import get_session
from database.models import User

# Import callback handlers
from .pokemart_callbacks.pokemart_main_menu import pokemart_main_menu
from .pokemart_callbacks.pokemart_event_cards import pokemart_event_cards
from .pokemart_callbacks.pokemart_capturas import pokemart_capturas

router = Router()

# Register callback handlers
router.callback_query.register(pokemart_main_menu, lambda call: call.data == "pokemart_main_menu")
router.callback_query.register(pokemart_event_cards, lambda call: call.data == "pokemart_event_cards")
router.callback_query.register(pokemart_capturas, lambda call: call.data.startswith("pokemart_capturas"))


@router.message(Command(commands=["pokemart", "pokem"]))
async def pokemart_command(message: types.Message):
    """
    Displays the main Pokémart menu.
    """
    if message.chat.type != "private":
        await message.reply(
            "❌ Este comando não está disponível em grupos.\n"
            "Por favor, use este comando em uma conversa privada com o bot.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    try:
        await pokemart_main_menu(message)
    except Exception as e:
        await message.reply(
            "❌ Ocorreu um erro ao processar sua solicitação. Por favor, tente novamente mais tarde.",
            parse_mode=ParseMode.MARKDOWN,
        )
        # Optionally log the error for debugging purposes
        print(f"Error in pokemart_command: {e}")