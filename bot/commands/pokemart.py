from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from sqlalchemy.future import select
from database.session import get_session
from database.models import User

# Import callback handlers from the submodules
from .pokemart_callbacks.pokemart_main_menu import pokemart_main_menu
from .pokemart_callbacks.pokemart_event_cards import pokemart_event_cards
from .pokemart_callbacks.pokemart_capturas import router as capturas_router
from .pokemart_callbacks.pokemart_help_capturas import router as help_capturas_router

router = Router()

# Register the main callbacks for event cards and main menu
router.callback_query.register(pokemart_main_menu, lambda call: call.data == "pokemart_main_menu")
router.callback_query.register(pokemart_event_cards, lambda call: call.data == "pokemart_event_cards")

# Include the "capturas" router and the "help_capturas" router
router.include_router(capturas_router)
router.include_router(help_capturas_router)

@router.message(Command(commands=["pokemart", "pokem"]))
async def pokemart_command(message: types.Message):
    """
    Displays the main Pokémart menu if user only typed /pokemart (no subcommands).
    Otherwise, the subcommand logic in pokemart_capturas.py can intercept.
    """
    # If user typed "/pokemart capturas ..." => that subcommand logic is triggered by the
    # `pokemart_subcommand_handler` in pokemart_capturas.py. So do nothing here if more text is present.
    text_parts = message.text.split(maxsplit=1)
    # If there's more text after /pokemart, let subcommand handle it. If not => show main menu
    if len(text_parts) > 1:
        # There's an argument. The "pokemart_subcommand_handler" is already registered in pokemart_capturas
        # so we just return to allow that handler to do its work.
        return

    # No extra text => show main menu
    try:
        await pokemart_main_menu(message)
    except Exception as e:
        await message.reply(
            "❌ Ocorreu um erro ao processar sua solicitação. Tente novamente mais tarde.",
            parse_mode=ParseMode.MARKDOWN,
        )
        print(f"Error in pokemart_command: {e}")
