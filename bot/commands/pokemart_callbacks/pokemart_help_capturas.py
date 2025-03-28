from aiogram import types, Router
from aiogram.enums import ParseMode

router = Router()

async def help_buy_capturas(callback: types.CallbackQuery):
    """
    Displays help instructions for buying Capturas.
    """
    help_text = (
        "📖 **Como comprar Capturas:**\n\n"
        "Envie um comando no seguinte formato para comprar:\n\n"
        "```\n/pokemart capturas 5 x3, 6 x1\n```\n"
        "Isso significa que você deseja comprar 3 unidades do card com ID 5 "
        "e 1 unidade do card com ID 6.\n\n"
        "Certifique-se de ter pokecoins suficientes para a compra."
    )
    await callback.message.answer(help_text, parse_mode=ParseMode.MARKDOWN)

# Register the callback for the button: "help_buy_capturas"
router.callback_query.register(help_buy_capturas, lambda call: call.data == "help_buy_capturas")
