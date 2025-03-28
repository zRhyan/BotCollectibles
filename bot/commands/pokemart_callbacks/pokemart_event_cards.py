from aiogram import types
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.future import select
from database.session import get_session
from database.models import Card

async def pokemart_event_cards(callback: types.CallbackQuery):
    """
    Displays Event Cards (💎 rarity) available for purchase.
    """
    async with get_session() as session:
        result = await session.execute(select(Card).where(Card.rarity == "💎"))
        event_cards = result.scalars().all()
    if not event_cards:
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="⬅️ Voltar", callback_data="pokemart_main_menu")
        keyboard.adjust(1)
        await callback.message.edit_text(
            "🎟️ **Event Cards**\n\nNenhum card de evento está disponível no momento.",
            reply_markup=keyboard.as_markup(),
            parse_mode=ParseMode.MARKDOWN
        )
        return

    text = "🎟️ **Event Cards**\n\nEscolha um card para comprar:\n\n"
    keyboard = InlineKeyboardBuilder()
    for card in event_cards:
        keyboard.button(
            text=f"{card.name} - {card.price} pokecoins",
            callback_data=f"buy_event_card_{card.id}"
        )
    keyboard.button(text="⬅️ Voltar", callback_data="pokemart_main_menu")
    keyboard.adjust(1)
    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode=ParseMode.MARKDOWN)
