from math import ceil
from aiogram import Router, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func
from sqlalchemy.orm import joinedload
from database.session import get_session
from database.models import User, Card, Marketplace, Inventory

router = Router()

# Number of listings per page
PAGE_SIZE = 5
# Temporary store for pending purchase orders keyed by buyer id.
pending_purchase = {}

@router.message(Command(commands=["pokemart", "pokem"]))
async def pokemart_command(message: types.Message):
    """
    Displays the main Pokémart menu.
    (This command is only available in private chats.)
    """
    if message.chat.type != "private":
        await message.reply(
            "❌ Este comando não está disponível em grupos.\n"
            "Por favor, use este comando em uma conversa privada com o bot.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

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
        f"💰 **Suas pokecoins:** {coins}\n\n"
        "Escolha uma das opções abaixo:"
    )
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🎟️ CARDS ESPECIAIS", callback_data="pokemart_event_cards")
    keyboard.button(text="🃏 CAPTURAS", callback_data="pokemart_capturas")
    keyboard.adjust(1)
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
        f"💰 **Suas pokecoins:** {coins}\n\n"
        "Escolha uma das opções abaixo:"
    )
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🎟️ CARDS ESPECIAIS", callback_data="pokemart_event_cards")
    keyboard.button(text="🃏 CAPTURAS", callback_data="pokemart_capturas")
    keyboard.adjust(1)
    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode=ParseMode.MARKDOWN)


@router.callback_query(lambda call: call.data == "pokemart_event_cards")
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


@router.callback_query(lambda call: call.data.startswith("pokemart_capturas"))
async def pokemart_capturas(callback: types.CallbackQuery):
    """
    Displays a paginated list of Capturas (cards sold by users)
    available for purchase. Also shows instructions on how to comprar.
    """
    # Show page 1 initially
    await show_capturas_page(callback, page=1)


@router.callback_query(lambda call: call.data.startswith("capturas_page_"))
async def capturas_page(callback: types.CallbackQuery):
    """
    Handles pagination for Capturas listings.
    Callback data format: "capturas_page_{page}"
    """
    try:
        page = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer("Página inválida.", show_alert=True)
        return
    await show_capturas_page(callback, page=page)


async def show_capturas_page(callback: types.CallbackQuery, page: int):
    """
    Helper function to display marketplace listings with pagination.
    """
    async with get_session() as session:
        # Count total listings matching normal rarities.
        count_result = await session.execute(
            select(func.count()).select_from(
                select(Marketplace)
                .join(Marketplace.card)
                .where(Card.rarity.in_(["🥇", "🥈", "🥉"]))
                .subquery()
            )
        )
        total_listings = count_result.scalar() or 0
        total_pages = ceil(total_listings / PAGE_SIZE) if total_listings > 0 else 1

        # Retrieve listings for the current page with eager loading of card.
        result = await session.execute(
            select(Marketplace)
            .options(joinedload(Marketplace.card))
            .join(Marketplace.card)
            .where(Card.rarity.in_(["🥇", "🥈", "🥉"]))
            .limit(PAGE_SIZE)
            .offset((page - 1) * PAGE_SIZE)
        )
        listings = result.scalars().all()

    if not listings:
        text = "🃏 **Capturas**\n\nNenhum card está à venda no momento."
    else:
        text = "🃏 **Capturas**\n\n"
        for listing in listings:
            # listing.card is eagerly loaded.
            text += f"{listing.card.rarity} **{listing.card.id}. {listing.card.name}** - `{listing.price}` pokecoins\n"
        text += (
            "\nPara comprar, envie o comando:\n"
            "`/pokemart capturas <ID xQuantidade, ...>`\n"
            "Exemplo: `/pokemart capturas 5 x3, 6 x1`"
        )

    # Build pagination and help keyboard.
    keyboard = InlineKeyboardBuilder()
    if page > 1:
        keyboard.button(text="⬅️ Anterior", callback_data=f"capturas_page_{page-1}")
    if page < total_pages:
        keyboard.button(text="Próxima ➡️", callback_data=f"capturas_page_{page+1}")
    keyboard.button(text="⬅️ Voltar", callback_data="pokemart_main_menu")
    # Add a note button (informative only).
    keyboard.button(text="❓ Como comprar?", callback_data="help_buy_capturas")
    keyboard.adjust(1)
    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode=ParseMode.MARKDOWN)


@router.callback_query(lambda call: call.data == "help_buy_capturas")
async def help_buy_capturas(callback: types.CallbackQuery):
    """
    Displays help text explaining how to buy cards from CAPTURAS.
    """
    help_text = (
        "📖 **Como comprar Capturas:**\n\n"
        "Para comprar cards vendidos por usuários, envie um comando no seguinte formato:\n\n"
        "```\n/pokemart capturas 5 x3, 6 x1\n```\n"
        "Isso significa que você deseja comprar 3 unidades do card com ID 5 e 1 unidade do card com ID 6.\n\n"
        "Certifique-se de ter pokecoins suficientes para a compra."
    )
    await callback.answer(help_text, show_alert=True)


@router.message(Command("pokemart"))
async def pokemart_capturas_purchase(message: types.Message):
    """
    Handles purchase orders for CAPTURAS.
    Expected format:
      /pokemart capturas <ID xQuantidade, ...>
    """
    text = message.text.strip()
    parts = text.split(maxsplit=2)
    if len(parts) < 3 or parts[1].lower() != "capturas":
        return  # Not a purchase command
    order_str = parts[2].strip()
    orders = []
    for item in order_str.split(","):
        try:
            card_id_str, quantity_str = item.strip().split("x")
            card_id = int(card_id_str)
            quantity = int(quantity_str)
            orders.append((card_id, quantity))
        except ValueError:
            await message.reply(
                f"❌ **Erro:** Formato inválido para o item `{item}`. Use o formato `ID xQuantidade`.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

    # Verify availability and calculate total cost.
    async with get_session() as session:
        total_cost = 0
        for card_id, quantity in orders:
            result = await session.execute(
                select(func.count()).select_from(
                    select(Marketplace)
                    .options(joinedload(Marketplace.card))
                    .where(Marketplace.card_id == card_id)
                    .subquery()
                )
            )
            available = result.scalar() or 0
            if available < quantity:
                await message.reply(
                    f"❌ **Erro:** Não há listings suficientes para o card ID `{card_id}`. Disponível: `{available}`.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            # Get price from one listing.
            result = await session.execute(
                select(Marketplace)
                .options(joinedload(Marketplace.card))
                .where(Marketplace.card_id == card_id)
                .limit(1)
            )
            listing = result.scalar_one_or_none()
            if listing is None:
                await message.reply(
                    f"❌ **Erro:** Nenhuma listing encontrada para o card ID `{card_id}`.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            total_cost += listing.price * quantity

        # Check buyer's coin balance.
        result = await session.execute(select(User).where(User.id == message.from_user.id))
        buyer = result.scalar_one_or_none()
        if not buyer:
            await message.reply(
                "❌ **Erro:** Usuário não encontrado.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        if buyer.coins < total_cost:
            await message.reply(
                f"❌ **Erro:** Moedas insuficientes. Você precisa de `{total_cost}` pokecoins, mas possui apenas `{buyer.coins}`.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

    # Store the purchase order for confirmation.
    pending_purchase[message.from_user.id] = orders

    # Build a confirmation message.
    confirm_text = "⚠️ **Confirmação de Compra**\n\nVocê está prestes a comprar:\n\n"
    for card_id, quantity in orders:
        async with get_session() as session:
            result = await session.execute(
                select(Marketplace)
                .options(joinedload(Marketplace.card))
                .where(Marketplace.card_id == card_id)
                .limit(1)
            )
            listing = result.scalar_one_or_none()
        if listing:
            confirm_text += f"{listing.card.rarity} **{listing.card.id}. {listing.card.name}** - `{quantity}` unidades\n"
    confirm_text += f"\n💵 **Total a pagar:** `{total_cost}` pokecoins\n\nDeseja confirmar a compra?"

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="✅ Confirmar", callback_data=f"confirm_buy_{message.from_user.id}")
    keyboard.button(text="❌ Cancelar", callback_data="cancel_buy")
    keyboard.adjust(1)
    await message.reply(confirm_text, reply_markup=keyboard.as_markup(), parse_mode=ParseMode.MARKDOWN)


@router.callback_query(lambda call: call.data.startswith("confirm_buy_"))
async def confirm_buy(callback: types.CallbackQuery):
    """
    Processes confirmation for buying capturas.
    Callback data format: "confirm_buy_{buyer_id}"
    """
    try:
        buyer_id = int(callback.data.split("_")[2])
    except (IndexError, ValueError):
        await callback.answer("Dados inválidos.", show_alert=True)
        return

    if buyer_id not in pending_purchase:
        await callback.answer("Nenhuma compra pendente encontrada.", show_alert=True)
        return
    orders = pending_purchase.pop(buyer_id)

    async with get_session() as session:
        result = await session.execute(select(User).where(User.id == buyer_id))
        buyer = result.scalar_one_or_none()
        if not buyer:
            await callback.answer("Usuário não encontrado.", show_alert=True)
            return

        total_cost = 0
        # Process each order: remove listings and add cards to buyer's inventory.
        for card_id, quantity in orders:
            result = await session.execute(
                select(Marketplace)
                .options(joinedload(Marketplace.card))
                .where(Marketplace.card_id == card_id)
                .limit(quantity)
            )
            listings = result.scalars().all()
            if len(listings) < quantity:
                await callback.answer(f"❌ Erro: Listings insuficientes para o card ID {card_id}.", show_alert=True)
                return
            for listing in listings:
                price = listing.price  # Price is assumed consistent.
                total_cost += price
                await session.delete(listing)
                # Add card to buyer's inventory.
                result = await session.execute(
                    select(Inventory).where(Inventory.user_id == buyer_id, Inventory.card_id == card_id)
                )
                inv_item = result.scalar_one_or_none()
                if inv_item:
                    inv_item.quantity += 1
                else:
                    new_inv = Inventory(user_id=buyer_id, card_id=card_id, quantity=1)
                    session.add(new_inv)
        buyer.coins -= total_cost
        await session.commit()

    await callback.message.edit_text(
        f"✅ **Compra concluída!** Você gastou `{total_cost}` pokecoins e recebeu os cards comprados.",
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer("Compra realizada com sucesso!", show_alert=True)


@router.callback_query(lambda call: call.data == "cancel_buy")
async def cancel_buy(callback: types.CallbackQuery):
    """
    Cancels any pending purchase action.
    """
    buyer_id = callback.from_user.id
    if buyer_id in pending_purchase:
        pending_purchase.pop(buyer_id)
    await callback.message.edit_text("❌ Compra cancelada.", parse_mode=ParseMode.MARKDOWN)
    await callback.answer("Compra cancelada.", show_alert=True)
