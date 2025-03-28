from aiogram import types, Router
from aiogram.enums import ParseMode

router = Router()

async def help_buy_capturas(callback: types.CallbackQuery):
    """
    Displays help instructions for buying Capturas in the new button-based flow.
    """
    help_text = (
        "📖 **Como comprar Capturas:**\n\n"
        "1. Clique em **Comprar Cards**.\n"
        "2. Será enviada uma nova mensagem solicitando que você informe o(s) card(s) e quantidade(s).\n"
        "   Formato: `ID xQuantidade, ID xQuantidade, ...`\n"
        "   Exemplo: `1 x3, 4 x2`\n\n"
        "3. O bot calculará o custo total e perguntará se deseja confirmar ou cancelar.\n"
        "4. Ao confirmar, as cartas serão compradas (se disponíveis) e adicionadas ao seu inventário."
    )
    # Instead of editing, we'll send a new message so user can still see the listing
    await callback.message.answer(help_text, parse_mode=ParseMode.MARKDOWN)

# Register the callback for the button: "help_buy_capturas"
router.callback_query.register(help_buy_capturas, lambda call: call.data == "help_buy_capturas")
