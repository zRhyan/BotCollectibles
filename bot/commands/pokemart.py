from aiogram import Router, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select
from database.session import get_session
from database.models import User, Card, Marketplace

router = Router()

@router.message(Command(commands=["pokemart", "pokem"]))
async def pokemart_command(message: types.Message):
    """
    Handles the /pokemart (or /pokem) command.
    Displays the main menu for the Pokémart.
    """
    user_id = message.from_user.id

    # Fetch the user's nickname and coins
    async with get_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            await message.reply(
                "❌ **Erro:** Você ainda não está registrado no sistema. Use o comando `/jornada` para começar sua aventura.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        nickname = user.nickname
        coins = user.coins

    # Create the main menu
    text = (
        f"👋 Olá, **{nickname}**! Encontrei alguns produtos à venda, o que deseja comprar?\n\n"
        f"💰 **Suas moedas:** {coins}\n\n"
        f"Escolha uma das opções abaixo:"
    )

    # Inline keyboard with options
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton(text="🎟️ EVENT CARDS", callback_data="pokemart_event_cards"),
        InlineKeyboardButton(text="🃏 CAPTURAS", callback_data="pokemart_capturas"),
        InlineKeyboardButton(text="⚪ POKÉBOLAS", callback_data="pokemart_pokebolas")
    )

    await message.reply(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)

@router.callback_query(lambda call: call.data == "pokemart_event_cards")
async def pokemart_event_cards(callback: types.CallbackQuery):
    """
    Displays the list of event cards (💎 rarity) available for purchase.
    """
    async with get_session() as session:
        result = await session.execute(select(Card).where(Card.rarity == "💎"))
        event_cards = result.scalars().all()

    if not event_cards:
        await callback.message.edit_text(
            "🎟️ **Event Cards**\n\n"
            "Nenhum card de evento está disponível no momento.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    text = "🎟️ **Event Cards**\n\nEscolha um card para comprar:\n\n"
    keyboard = InlineKeyboardMarkup(row_width=1)

    for card in event_cards:
        keyboard.add(
            InlineKeyboardButton(
                text=f"{card.name} - {card.price} moedas",
                callback_data=f"buy_event_card_{card.id}"
            )
        )

    keyboard.add(InlineKeyboardButton(text="⬅️ Voltar", callback_data="pokemart_main_menu"))

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)

@router.callback_query(lambda call: call.data == "pokemart_capturas")
async def pokemart_capturas(callback: types.CallbackQuery):
    """
    Displays the list of normal cards (🥇, 🥈, 🥉 rarities) for sale by other users.
    """
    async with get_session() as session:
        result = await session.execute(
            select(Marketplace).join(Marketplace.card).where(Card.rarity.in_(["🥇", "🥈", "🥉"]))
        )
        listings = result.scalars().all()

    if not listings:
        await callback.message.edit_text(
            "🃏 **Capturas**\n\n"
            "Nenhum card está à venda no momento.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    text = "🃏 **Capturas**\n\nEscolha um card para comprar:\n\n"
    keyboard = InlineKeyboardMarkup(row_width=1)

    for listing in listings:
        keyboard.add(
            InlineKeyboardButton(
                text=f"{listing.card.name} - {listing.price} moedas",
                callback_data=f"buy_marketplace_card_{listing.id}"
            )
        )

    keyboard.add(InlineKeyboardButton(text="⬅️ Voltar", callback_data="pokemart_main_menu"))

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)