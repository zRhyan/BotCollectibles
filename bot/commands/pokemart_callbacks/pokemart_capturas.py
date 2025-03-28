from math import ceil
from aiogram import types, Router, F
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func
from sqlalchemy.orm import joinedload

from database.session import get_session
from database.models import User, Marketplace, Inventory, Card

# Number of marketplace listings to show per page
PAGE_SIZE = 5

# 1) Temporary store for user "state" => which step they're in
user_states = {}  # { user_id: "waiting_for_cards_input" | None }

# 2) Store purchase details (card ids and quantities) for confirmation
pending_purchase = {}  # { user_id: [ (card_id, quantity), ... ] }

##############################################################################
#  A) DISPLAYING & PAGINATING CAPTURAS
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

    # Build inline keyboard:
    keyboard = InlineKeyboardBuilder()
    # Pagination
    if page > 1:
        keyboard.button(text="⬅️ Anterior", callback_data=f"capturas_page_{page-1}")
    if page < total_pages:
        keyboard.button(text="Próxima ➡️", callback_data=f"capturas_page_{page+1}")

    # "Comprar Cards" -> triggers user to provide "1 x3, 4 x2," etc.
    keyboard.button(text="🛒 Comprar Cards", callback_data="capturas_buy_cards")
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
    """
    try:
        page = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer("Página inválida.", show_alert=True)
        return
    await show_capturas_page(callback, page=page)

##############################################################################
# B) FLOW FOR BUYING CARDS
##############################################################################

async def capturas_buy_cards(callback: types.CallbackQuery):
    """
    Triggered when user clicks "Comprar Cards" in the Capturas menu.
    We set the user's state to waiting_for_cards_input,
    and prompt them to enter "ID xQuantidade" pairs.
    """
    user_id = callback.from_user.id
    user_states[user_id] = "waiting_for_cards_input"

    await callback.message.edit_text(
        "🤔 **Qual card você deseja comprar?**\n"
        "Envie uma mensagem neste formato, por exemplo:\n\n"
        "`1 x3, 4 x5`\n"
        "Isso significa 3 cards do card_id=1 e 5 cards do card_id=4.\n\n"
        "Envie agora:",
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer()

async def capturas_cards_input(message: types.Message):
    """
    This receives the user's typed input of "ID xQuantidade" pairs.
    Then we parse it, check availability, store for confirmation, and show the confirm message.
    """
    user_id = message.from_user.id

    # Check if user is actually in waiting_for_cards_input state
    if user_states.get(user_id) != "waiting_for_cards_input":
        return  # ignore this message if they're not in that state

    # user typed something like: "1 x3, 4 x5"
    raw_text = message.text.strip()
    items = raw_text.split(",")

    orders = []
    for item in items:
        try:
            card_id_str, qty_str = item.strip().split("x")
            card_id = int(card_id_str)
            quantity = int(qty_str)
            orders.append((card_id, quantity))
        except ValueError:
            await message.reply(
                f"❌ **Erro:** Formato inválido em `{item}`. Use: `ID xQuantidade`.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

    # We'll check availability + cost
    async with get_session() as session:
        total_cost = 0
        for (card_id, qty) in orders:
            # how many single listings are available?
            cnt_q = select(func.count(Marketplace.id)).where(Marketplace.card_id == card_id)
            result = await session.execute(cnt_q)
            available = result.scalar() or 0
            if available < qty:
                await message.reply(
                    f"❌ **Erro:** Você pediu `{qty}` do card ID `{card_id}`, mas só há `{available}` disponível.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

            # get the price from one listing (assuming same price for that card id)
            listing_q = select(Marketplace).where(Marketplace.card_id == card_id).limit(1)
            result = await session.execute(listing_q)
            single_list = result.scalar_one_or_none()
            if not single_list:
                await message.reply(
                    f"❌ **Erro:** Nenhuma listing para card ID `{card_id}`.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            total_cost += single_list.price * qty

        # Check buyer's coin balance
        buyer_q = select(User).where(User.id == user_id)
        result = await session.execute(buyer_q)
        buyer = result.scalar_one_or_none()
        if not buyer:
            await message.reply(
                "❌ **Erro:** Você ainda não se registrou. Use `/jornada`.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        if buyer.coins < total_cost:
            await message.reply(
                f"❌ **Erro:** Você precisa de `{total_cost}` pokecoins, mas tem `{buyer.coins}`.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

    # If successful => store in pending_purchase, user leaves the input state
    pending_purchase[user_id] = orders
    user_states[user_id] = None  # reset their state

    # Summarize
    confirm_text = "⚠️ **Confirmação de Compra**\n\nVocê quer comprar:\n\n"
    async with get_session() as session:
        for (card_id, qty) in orders:
            listing_q = (
                select(Marketplace)
                .options(joinedload(Marketplace.card))
                .where(Marketplace.card_id == card_id).limit(1)
            )
            result = await session.execute(listing_q)
            listing = result.scalar_one_or_none()
            if listing:
                confirm_text += f"{listing.card.rarity} **{listing.card.id}. {listing.card.name}** - `{qty}` unidades\n"
    confirm_text += f"\n💵 **Total:** `{total_cost}` pokecoins\n\nDeseja confirmar a compra?"

    # inline keyboard => confirm or cancel
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Confirmar", callback_data=f"confirm_buy_{user_id}")
    kb.button(text="❌ Cancelar", callback_data="cancel_buy")
    kb.adjust(1)

    await message.reply(confirm_text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb.as_markup())

async def confirm_buy(callback: types.CallbackQuery):
    """
    Final step: remove the listings from marketplace, add cards to user,
    deduct cost from user’s coins, etc.
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
        # get buyer
        buyer_q = select(User).where(User.id == buyer_id)
        result = await session.execute(buyer_q)
        buyer = result.scalar_one_or_none()
        if not buyer:
            await callback.answer("Usuário não encontrado.", show_alert=True)
            return

        # remove the listings from marketplace
        for (card_id, qty) in orders:
            listings_q = select(Marketplace).where(Marketplace.card_id == card_id).limit(qty)
            result = await session.execute(listings_q)
            these_listings = result.scalars().all()
            if len(these_listings) < qty:
                await callback.answer(
                    f"❌ Erro: não há `{qty}` listings disponíveis para card ID {card_id}.",
                    show_alert=True
                )
                return
            for listing in these_listings:
                total_cost += listing.price
                await session.delete(listing)

                # add to buyer's inventory
                inv_q = select(Inventory).where(Inventory.user_id == buyer_id, Inventory.card_id == card_id)
                inv_res = await session.execute(inv_q)
                inv_item = inv_res.scalar_one_or_none()
                if inv_item:
                    inv_item.quantity += 1
                else:
                    new_inv = Inventory(user_id=buyer_id, card_id=card_id, quantity=1)
                    session.add(new_inv)

        # check if buyer has enough coins (again, in case time passed)
        if buyer.coins < total_cost:
            await callback.answer(
                f"❌ Moedas insuficientes para o custo final de {total_cost}!",
                show_alert=True
            )
            return
        buyer.coins -= total_cost
        await session.commit()

    # success
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
#  ROUTER & REGISTRATIONS
##############################################################################

router = Router()

# Callback for pagination
router.callback_query.register(capturas_page, lambda call: call.data.startswith("capturas_page_"))
# Callback for "Comprar Cards" button
router.callback_query.register(capturas_buy_cards, lambda call: call.data == "capturas_buy_cards")

# Confirm/cancel purchase
router.callback_query.register(confirm_buy, lambda call: call.data.startswith("confirm_buy_"))
router.callback_query.register(cancel_buy, lambda call: call.data == "cancel_buy")

# Show CAPTURAS listings
router.callback_query.register(pokemart_capturas, lambda call: call.data.startswith("pokemart_capturas"))

# The text input from user for "ID xQuantidade"
# We'll use a normal message handler with no command filter, but check user_states
router.message.register(capturas_cards_input, F.text)
