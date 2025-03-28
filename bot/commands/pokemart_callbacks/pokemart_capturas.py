from math import ceil
from aiogram import types, Router, F
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func
from sqlalchemy.orm import joinedload

from database.session import get_session
from database.models import User, Marketplace, Inventory, Card

PAGE_SIZE = 5

# user_states => whether the user is waiting to input "card_id x quantity" lines
user_states = {}  # { user_id: "waiting_for_cards_input" | None }

# Store purchase details for each user
pending_purchase = {}  # { user_id: [ (card_id, qty), ... ] }

##############################################################################
# 1) Show / Paginate CAPTURAS
##############################################################################

async def pokemart_capturas(callback: types.CallbackQuery):
    await show_capturas_page(callback, 1)

async def show_capturas_page(callback: types.CallbackQuery, page: int):
    async with get_session() as session:
        # Count how many distinct "grouped" listings
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

        # Query page items
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

    # Build text
    if not rows:
        text = "🃏 **Capturas**\n\nNenhum card está à venda no momento."
    else:
        text = "🃏 **Capturas**\n\n"
        for r in rows:
            text += (
                f"{r.card_rarity} **{r.card_id}. {r.card_name}** "
                f"- `{r.card_price}` pokecoins "
                f"(x{r.available} disponíveis)\n"
            )

    # Inline keyboard
    keyboard = InlineKeyboardBuilder()
    if page > 1:
        keyboard.button(text="⬅️ Anterior", callback_data=f"capturas_page_{page-1}")
    if page < total_pages:
        keyboard.button(text="Próxima ➡️", callback_data=f"capturas_page_{page+1}")

    # Add "Comprar Cards" button
    keyboard.button(text="🛒 Comprar Cards", callback_data="capturas_buy_cards")
    keyboard.button(text="⬅️ Voltar", callback_data="pokemart_main_menu")
    keyboard.button(text="❓ COMO COMPRAR", callback_data="help_buy_capturas")
    keyboard.adjust(1)

    await callback.message.edit_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard.as_markup()
    )

async def capturas_page(callback: types.CallbackQuery):
    try:
        page = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer("Página inválida.", show_alert=True)
        return
    await show_capturas_page(callback, page)

##############################################################################
# 2) Buy Cards Flow
##############################################################################

async def capturas_buy_cards(callback: types.CallbackQuery):
    """
    Triggered when user clicks "Comprar Cards".
    Sets user state to waiting_for_cards_input, and prompts user to type the ID/qty lines.
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
    Receives the text "ID xQuantidade, ID xQuantidade" from user.
    Checks availability, then shows confirmation inline keyboard.
    """
    user_id = message.from_user.id
    if user_states.get(user_id) != "waiting_for_cards_input":
        return  # ignore if user is not in that state

    raw_text = message.text.strip()
    items = raw_text.split(",")

    orders = []
    for item in items:
        try:
            card_id_str, qty_str = item.strip().split("x")
            card_id = int(card_id_str)
            qty = int(qty_str)
            orders.append((card_id, qty))
        except ValueError:
            await message.reply(
                f"❌ **Erro:** Formato inválido em `{item}`. Use: `ID xQuantidade`.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

    # Check availability
    async with get_session() as session:
        total_cost = 0
        for (card_id, q) in orders:
            ccount_q = select(func.count(Marketplace.id)).where(Marketplace.card_id == card_id)
            res = await session.execute(ccount_q)
            available = res.scalar() or 0
            if available < q:
                await message.reply(
                    f"❌ **Erro:** Você pediu `{q}` do card `{card_id}`, mas só há `{available}` disponível.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            # get price from one listing
            single_q = select(Marketplace).where(Marketplace.card_id == card_id).limit(1)
            res = await session.execute(single_q)
            single_list = res.scalar_one_or_none()
            if not single_list:
                await message.reply(
                    f"❌ **Erro:** Nenhuma listing para card ID `{card_id}`.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            total_cost += single_list.price * q

        buyer_q = select(User).where(User.id == user_id)
        res = await session.execute(buyer_q)
        buyer = res.scalar_one_or_none()
        if not buyer:
            await message.reply(
                "❌ **Erro:** Você não está registrado. Use `/jornada`.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        if buyer.coins < total_cost:
            await message.reply(
                f"❌ **Erro:** Você precisa de `{total_cost}` pokecoins, mas tem `{buyer.coins}`.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

    # If success, store orders, reset user state
    user_states[user_id] = None
    pending_purchase[user_id] = orders

    # Summarize
    confirm_text = "⚠️ **Confirmação de Compra**\n\nVocê quer comprar:\n\n"
    async with get_session() as session:
        for (card_id, q) in orders:
            listing_q = select(Marketplace).options(joinedload(Marketplace.card)).where(Marketplace.card_id == card_id).limit(1)
            res = await session.execute(listing_q)
            listing = res.scalar_one_or_none()
            if listing:
                confirm_text += (
                    f"{listing.card.rarity} **{listing.card.id}. {listing.card.name}** - `{q}` unidades\n"
                )
    confirm_text += f"\n💵 **Total:** `{total_cost}` pokecoins\n\nDeseja confirmar a compra?"

    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Confirmar", callback_data=f"confirm_buy_{user_id}")
    kb.button(text="❌ Cancelar", callback_data="cancel_buy")
    kb.adjust(1)
    await message.reply(confirm_text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb.as_markup())

async def confirm_buy(callback: types.CallbackQuery):
    """
    Final step: remove the listings, add cards to buyer, deduct coins, etc.
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
        buyer_q = select(User).where(User.id == buyer_id)
        res = await session.execute(buyer_q)
        buyer = res.scalar_one_or_none()
        if not buyer:
            await callback.answer("Usuário não encontrado.", show_alert=True)
            return

        for (card_id, q) in orders:
            listing_q = select(Marketplace).where(Marketplace.card_id == card_id).limit(q)
            res = await session.execute(listing_q)
            these = res.scalars().all()
            if len(these) < q:
                await callback.answer(f"❌ Erro: só há {len(these)} listings para card {card_id}.", show_alert=True)
                return
            for listing in these:
                total_cost += listing.price
                await session.delete(listing)
                # inventory
                inv_q = select(Inventory).where(Inventory.user_id == buyer_id, Inventory.card_id == card_id)
                ires = await session.execute(inv_q)
                inv_item = ires.scalar_one_or_none()
                if inv_item:
                    inv_item.quantity += 1
                else:
                    new_inv = Inventory(user_id=buyer_id, card_id=card_id, quantity=1)
                    session.add(new_inv)

        # check coins
        if buyer.coins < total_cost:
            await callback.answer(f"❌ Moedas insuficientes para {total_cost}!", show_alert=True)
            return
        buyer.coins -= total_cost
        await session.commit()

    await callback.message.edit_text(
        f"✅ **Compra concluída!**\nVocê gastou `{total_cost}` pokecoins e recebeu os cards.",
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer("Compra realizada com sucesso!", show_alert=True)

async def cancel_buy(callback: types.CallbackQuery):
    buyer_id = callback.from_user.id
    if buyer_id in pending_purchase:
        pending_purchase.pop(buyer_id)
    await callback.message.edit_text("❌ Compra cancelada.", parse_mode=ParseMode.MARKDOWN)
    await callback.answer("Compra cancelada.", show_alert=True)

##############################################################################
# 3) Router & Registration
##############################################################################

router = Router()

# Pagination
router.callback_query.register(capturas_page, lambda c: c.data.startswith("capturas_page_"))
# "Comprar Cards" button
router.callback_query.register(capturas_buy_cards, lambda c: c.data == "capturas_buy_cards")

# Confirm/cancel
router.callback_query.register(confirm_buy, lambda c: c.data.startswith("confirm_buy_"))
router.callback_query.register(cancel_buy, lambda c: c.data == "cancel_buy")

# Display CAPTURAS
router.callback_query.register(pokemart_capturas, lambda c: c.data.startswith("pokemart_capturas"))

# The text input for ID xQuantity
router.message.register(capturas_cards_input, F.text)
