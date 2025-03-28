from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from sqlalchemy.future import select
from database.session import get_session
from database.models import User

# Import callback handlers
from .pokemart_callbacks.pokemart_main_menu import pokemart_main_menu
from .pokemart_callbacks.pokemart_event_cards import pokemart_event_cards
from .pokemart_callbacks.pokemart_capturas import handle_capturas_subcommand
from .pokemart_callbacks.pokemart_capturas import router as capturas_router
from .pokemart_callbacks.pokemart_help_capturas import router as help_capturas_router

router = Router()

# Include the "capturas" routers (which handle callbacks & pending purchase)
router.include_router(capturas_router)
router.include_router(help_capturas_router)

# Register these 2 callbacks for returning to main menu and showing event cards
router.callback_query.register(pokemart_main_menu, lambda call: call.data == "pokemart_main_menu")
router.callback_query.register(pokemart_event_cards, lambda call: call.data == "pokemart_event_cards")


@router.message(Command(commands=["pokemart", "pokem"]))
async def pokemart_command(message: types.Message):
    """
    This single handler deals with both:
      • /pokemart     => show main menu
      • /pokemart capturas ... => handle subcommand
    """
    # If user typed "/pokemart" alone => show the main menu
    text_parts = message.text.split(maxsplit=1)
    if len(text_parts) == 1:
        # no arguments => main menu
        await show_main_menu_or_error(message)
        return

    # If there is a second token, we check if it’s "capturas"
    args = text_parts[1].strip()  # everything after /pokemart
    if args.lower().startswith("capturas"):
        # Let the subcommand logic parse "capturas 5 x3, 6 x1" and do the purchase flow
        await handle_capturas_subcommand(message)
    else:
        # The user typed something else: /pokemart blah
        # You can decide what to do: show error or show main menu.
        await show_main_menu_or_error(message)


async def show_main_menu_or_error(message: types.Message):
    """
    Reusable helper that tries to show the main pokemart menu
    or prints an error if something fails.
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
        print(f"Error in pokemart_command: {e}")
