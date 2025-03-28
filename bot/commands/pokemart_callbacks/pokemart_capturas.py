from math import ceil
from aiogram import types, Router
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func
from sqlalchemy.orm import joinedload
from database.session import get_session
from database.models import User, Marketplace, Inventory, Card

# Number of listings per page
PAGE_SIZE = 5

# Temporary store for pending purchase orders (keyed by buyer id)
pending_purchase = {}

##############################################################################
# 1) DISPLAYING & PAGINATING CAPTURAS
##############################################################################

async def pokemart_capturas(callback: types.CallbackQuery):
    """
    Displays a paginated list of Capturas (cards sold by users).
    Shows how many copies are available for each card (aggregated).
    """
    await show_capturas_page(callback, page=1)

async def show_capturas_page(callback: types.CallbackQuery, page: int):
    """
    Helper function to display aggregated marketplace listings
    (grouping by card_id) with pagination.
    """
    async with get_session() as session:
        # Count how many distinct "grouped" listings are in normal rarities
        count_q = select(func.count(Card.id)).select_from(
            select(
                Card.id.label("card_id"),
                Card.name.label("card_name"),
                Card.rarity.label("card_rarity"),
                Marketplace.price.label("card_price"),
                func.count(Marketplace.id).label("available")
            )
            .join(Marketplace.card)
            .where(Card.rarity.in_(["🥇", "🥈", "🥉"]))
            .group_by(Card.id, Card.name, Card.rarity, Marketplace.price)
            .subquery()
        )
        count_result = await session.execute(count_q)
        total_listings = count_result.scalar() or 0
        total_pages = ceil(total_listings / PAGE_SIZE) if total_listings > 0 else 1

        # Query the aggregated results for the current page
        offset_val = (page - 1) * PAGE_SIZE
        listings_q = (
            select(
                Card.id.label("card_id"),
                Card.name.label("card_name"),
                Card.rarity.label("card_rarity"),
                Marketplace.price.label("card_price"),
                func.count(Marketplace.id).label("available")
            )
            .join(Marketplace.card)
            .where(Card.rarity.in_(["🥇", "🥈", "🥉"]))
            .group_by(Card.id, Card.name, Card.rarity, Marketplace.price)
            .limit(PAGE_SIZE)
            .offset(offset_val)
        )
        result = await session.execute(listings_q)
        rows = result.all()

    # Build the text
    if not rows:
        text = "🃏 **Capturas**\n\nNenhum card está à venda no momento."
    else:
        text = "🃏 **Capturas**\n\n"
        for row in rows:
            text += (
                f"{row.card_rarity} **{row.card_id}. {row.card_name}** "
                f"- `{row.card_price}` pokecoins "
                f"(x{row.available} disponíveis)\n"
            )

    # Build inline keyboard for pagination & “COMO COMPRAR” button
    keyboard = InlineKeyboardBuilder()
    # Pagination
    if page > 1:
        keyboard.button(text="⬅️ Anterior", callback_data=f"capturas_page_{page-1}")
    if page < total_pages:
        keyboard.button(text="Próxima ➡️", callback_data=f"capturas_page_{page+1}")
    # Return & help
    keyboard.button(text="⬅️ Voltar", callback_data="pokemart_main_menu")
    keyboard.button(text="❓ COMO COMPRAR", callback_data="help_buy_capturas")
    keyboard.adjust(1)

    await callback.message.edit_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard.as_markup()
    )

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

##############################################################################
# 2) CAPTURAS PURCHASE COMMAND + CONFIRMATION
##############################################################################

async def pokemart_subcommand_handler(message: types.Message):
    """
    Single handler for /pokemart commands.
    If user typed "/pokemart" with no args => do nothing, let main menu handle it.
    If user typed "/pokemart capturas ..." => parse purchase order.
    """
    text = message.text.strip()
    parts = text.split(maxsplit=2)
    # If user only typed /pokemart, or second token != "capturas", do nothing:
    # the main /pokemart can handle the menu.
    if len(parts) < 2 or parts[1].lower() != "capturas":
        return  # simply return

    # We have: /pokemart capturas ...
    if len(parts) < 3:
        await message.reply(
            "❗ **Erro:** faltam argumentos. Exemplo:\n"
            "`/pokemart capturas 5 x2, 9 x1`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    order_str = parts[2]
    orders = []
    for item in order_str.split(","):
        # each item = "ID xQuantidade"
        try:
            card_id_str, qty_str = item.strip().split("x")
            card_id = int(card_id_str)
            quantity = int(qty_str)
            orders.append((card_id, quantity))
        except ValueError:
            await message.reply(
                f"❌ **Erro:** Formato inválido para `{item}`. Use: `ID xQuantidade`.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

    # Check if user can buy that many
    async with get_session() as session:
        # sum the cost & verify each card's availability
        total_cost = 0
        for (card_id, qty) in orders:
            # Count how many single "listings" are available for this card_id
            ccount_q = select(func.count(Marketplace.id)).where(Marketplace.card_id == card_id)
            result = await session.execute(ccount_q)
            available = result.scalar() or 0
            if available < qty:
                await message.reply(
                    f"❌ **Erro:** Você pediu `{qty}` do card ID `{card_id}`, mas só há `{available}` disponível(s).",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

            # get the price from one listing (assuming the same price for all)
            listing_q = select(Marketplace).where(Marketplace.card_id == card_id).limit(1)
            result = await session.execute(listing_q)
            single_list = result.scalar_one_or_none()
            if not single_list:
                await message.reply(
                    f"❌ **Erro:** Nenhuma listing encontrada para card ID `{card_id}`.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            total_cost += single_list.price * qty

        # Check buyer's coin balance
        buyer_q = select(User).where(User.id == message.from_user.id)
        result = await session.execute(buyer_q)
        buyer = result.scalar_one_or_none()
        if not buyer:
            await message.reply(
                "❌ **Erro:** Usuário não encontrado. Registre-se com `/jornada`.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        if buyer.coins < total_cost:
            await message.reply(
                f"❌ **Erro:** Moedas insuficientes.\n"
                f"Precisa: `{total_cost}` pokecoins, tem apenas `{buyer.coins}`.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

    # If we got here, user can afford it and there are enough listings
    # Let's store the purchase in pending_purchase for confirmation
    pending_purchase[message.from_user.id] = orders

    # Build a confirmation text
    confirm_text = "⚠️ **Confirmação de Compra**\n\nVocê quer comprar:\n\n"
    async with get_session() as session:
        for (card_id, qty) in orders:
            # fetch a single listing to show card info
            listing_q = (
                select(Marketplace)
                .options(joinedload(Marketplace.card))
                .where(Marketplace.card_id == card_id)
                .limit(1)
            )
            result = await session.execute(listing_q)
            listing = result.scalar_one_or_none()
            if listing:
                confirm_text += (
                    f"{listing.card.rarity} **{listing.card.id}. {listing.card.name}** "
                    f"- `{qty}` unidades\n"
                )

    confirm_text += f"\n💵 **Total:** `{total_cost}` pokecoins\n\nDeseja confirmar a compra?"

    # Build inline keyboard
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Confirmar", callback_data=f"confirm_buy_{message.from_user.id}")
    kb.button(text="❌ Cancelar", callback_data="cancel_buy")
    kb.adjust(1)

    await message.reply(confirm_text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb.as_markup())

async def confirm_buy(callback: types.CallbackQuery):
    """
    Final step: remove the listings from marketplace, add cards to user,
    deduct cost from user’s coins.
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

    total_cost = 0
    async with get_session() as session:
        # Get buyer
        buyer_q = select(User).where(User.id == buyer_id)
        result = await session.execute(buyer_q)
        buyer = result.scalar_one_or_none()
        if not buyer:
            await callback.answer("Usuário não encontrado.", show_alert=True)
            return

        # For each card, remove exactly 'qty' marketplace rows
        for (card_id, qty) in orders:
            # get 'qty' rows
            listings_q = select(Marketplace).where(Marketplace.card_id == card_id).limit(qty)
            result = await session.execute(listings_q)
            these_listings = result.scalars().all()
            if len(these_listings) < qty:
                await callback.answer(
                    f"❌ Erro: não há `{qty}` listings disponíveis para card ID {card_id}.",
                    show_alert=True
                )
                return
            # Summation + remove from marketplace
            for listing in these_listings:
                total_cost += listing.price
                await session.delete(listing)
                # Add card to buyer's inventory
                inv_q = select(Inventory).where(Inventory.user_id == buyer_id, Inventory.card_id == card_id)
                inv_result = await session.execute(inv_q)
                inv_item = inv_result.scalar_one_or_none()
                if inv_item:
                    inv_item.quantity += 1
                else:
                    new_inv = Inventory(user_id=buyer_id, card_id=card_id, quantity=1)
                    session.add(new_inv)

        # Deduct coins
        if buyer.coins < total_cost:
            await callback.answer(
                f"❌ Moedas insuficientes para o custo final de {total_cost}!",
                show_alert=True
            )
            return
        buyer.coins -= total_cost
        await session.commit()

    await callback.message.edit_text(
        f"✅ **Compra concluída!**\nVocê gastou `{total_cost}` pokecoins e recebeu os cards.",
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer("Compra realizada com sucesso!", show_alert=True)

async def cancel_buy(callback: types.CallbackQuery):
    """
    Cancels any pending purchase action.
    """
    buyer_id = callback.from_user.id
    if buyer_id in pending_purchase:
        pending_purchase.pop(buyer_id)
    await callback.message.edit_text("❌ Compra cancelada.", parse_mode=ParseMode.MARKDOWN)
    await callback.answer("Compra cancelada.", show_alert=True)

##############################################################################
# 3) ROUTER & REGISTRATIONS
##############################################################################

router = Router()

# Remove old help_buy_capturas import/registration from here. (Now in pokemart_help_capturas.py)

router.message.register(pokemart_subcommand_handler, Command("pokemart"))

router.callback_query.register(capturas_page, lambda call: call.data.startswith("capturas_page_"))
router.callback_query.register(confirm_buy, lambda call: call.data.startswith("confirm_buy_"))
router.callback_query.register(cancel_buy, lambda call: call.data == "cancel_buy")

# This callback is triggered by the button with callback_data="pokemart_capturas"
router.callback_query.register(pokemart_capturas, lambda call: call.data.startswith("pokemart_capturas"))
