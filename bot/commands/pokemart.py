from aiogram import Router, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
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

    text = (
        f"👋 Olá, **{nickname}**! Encontrei alguns produtos à venda, o que deseja comprar?\n\n"
        f"💰 **Suas moedas:** {coins}\n\n"
        "Escolha uma das opções abaixo:"
    )

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🎟️ CARDS ESPECIAIS", callback_data="pokemart_event_cards")
    keyboard.button(text="🃏 CAPTURAS", callback_data="pokemart_capturas")
    keyboard.adjust(1)  # one button per row

    await message.reply(text, reply_markup=keyboard.as_markup(), parse_mode=ParseMode.MARKDOWN)


@router.callback_query(lambda call: call.data == "pokemart_main_menu")
async def pokemart_main_menu(callback: types.CallbackQuery):
    """
    Returns the user to the main Pokémart menu.
    """
    user_id = callback.from_user.id

    async with get_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            await callback.message.edit_text(
                "❌ **Erro:** Você ainda não está registrado no sistema. Use o comando `/jornada` para começar sua aventura.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        nickname = user.nickname
        coins = user.coins

    text = (
        f"👋 Olá, **{nickname}**! Encontrei alguns produtos à venda, o que deseja comprar?\n\n"
        f"💰 **Suas moedas:** {coins}\n\n"
        "Escolha uma das opções abaixo:"
    )

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🎟️ EVENT CARDS", callback_data="pokemart_event_cards")
    keyboard.button(text="🃏 CAPTURAS", callback_data="pokemart_capturas")
    keyboard.adjust(1)

    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode=ParseMode.MARKDOWN)


@router.callback_query(lambda call: call.data == "pokemart_event_cards")
async def pokemart_event_cards(callback: types.CallbackQuery):
    """
    Displays the list of Event Cards (💎 rarity) available for purchase.
    Includes a 'Voltar' button to return to the main menu.
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
        # Assumes that the Card model has a 'price' attribute.
        keyboard.button(
            text=f"{card.name} - {card.price} moedas",
            callback_data=f"buy_event_card_{card.id}"
        )
    keyboard.button(text="⬅️ Voltar", callback_data="pokemart_main_menu")
    keyboard.adjust(1)

    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode=ParseMode.MARKDOWN)


@router.callback_query(lambda call: call.data == "pokemart_capturas")
async def pokemart_capturas(callback: types.CallbackQuery):
    """
    Displays the list of Capturas (normal cards with 🥇, 🥈, 🥉 rarities) available for purchase.
    Includes a 'Voltar' button to return to the main menu.
    """
    async with get_session() as session:
        result = await session.execute(
            select(Marketplace)
            .join(Marketplace.card)
            .where(Card.rarity.in_(["🥇", "🥈", "🥉"]))
        )
        listings = result.scalars().all()

    if not listings:
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="⬅️ Voltar", callback_data="pokemart_main_menu")
        keyboard.adjust(1)
        await callback.message.edit_text(
            "🃏 **Capturas**\n\nNenhum card está à venda no momento.",
            reply_markup=keyboard.as_markup(),
            parse_mode=ParseMode.MARKDOWN
        )
        return

    text = "🃏 **Capturas**\n\nEscolha um card para comprar:\n\n"
    keyboard = InlineKeyboardBuilder()
    for listing in listings:
        keyboard.button(
            text=f"{listing.card.name} - {listing.price} moedas",
            callback_data=f"buy_marketplace_card_{listing.id}"
        )
    keyboard.button(text="⬅️ Voltar", callback_data="pokemart_main_menu")
    keyboard.adjust(1)

    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode=ParseMode.MARKDOWN)
