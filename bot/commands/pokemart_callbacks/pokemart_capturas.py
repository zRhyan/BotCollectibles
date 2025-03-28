from math import ceil
from aiogram import types
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func
from sqlalchemy.orm import joinedload
from database.session import get_session
from database.models import User, Marketplace, Inventory, Card
from aiogram.filters import Command
from aiogram.exceptions import SkipHandler

# Number of listings per page
PAGE_SIZE = 5
# Temporary store for pending purchase orders (keyed by buyer id)
pending_purchase = {}

async def pokemart_capturas(callback: types.CallbackQuery):
    """
    Displays a paginated list of Capturas (cards sold by users)
    available for purchase.
    """
    await show_capturas_page(callback, page=1)

async def show_capturas_page(callback: types.CallbackQuery, page: int):
    """
    Helper function to display marketplace listings with pagination.
    """
    async with get_session() as session:
        # Count total listings with normal rarities.
        count_result = await session.execute(
            select(func.count()).select_from(
                select(Marketplace)
                .join(Marketplace.card)
                .where(Marketplace.card.has(Marketplace.card.rarity.in_(["🥇", "🥈", "🥉"])))
                .subquery()
            )
        )
        total_listings = count_result.scalar() or 0
        total_pages = ceil(total_listings / PAGE_SIZE) if total_listings > 0 else 1

        result = await session.execute(
            select(Marketplace)
            .options(joinedload(Marketplace.card))
            .join(Marketplace.card)
            .where(Marketplace.card.has(Marketplace.card.rarity.in_(["🥇", "🥈", "🥉"])))
            .limit(PAGE_SIZE)
            .offset((page - 1) * PAGE_SIZE)
        )
        listings = result.scalars().all()

    if not listings:
        text = "🃏 **Capturas**\n\nNenhum card está à venda no momento."
    else:
        text = "🃏 **Capturas**\n\n"
        for listing in listings:
            text += f"{listing.card.rarity} **{listing.card.id}. {listing.card.name}** - `{listing.price}` pokecoins\n"
    # Build pagination and help keyboard.
    keyboard = InlineKeyboardBuilder()
    if page > 1:
        keyboard.button(text="⬅️ Anterior", callback_data=f"capturas_page_{page-1}")
    if page < total_pages:
        keyboard.button(text="Próxima ➡️", callback_data=f"capturas_page_{page+1}")
    keyboard.button(text="⬅️ Voltar", callback_data="pokemart_main_menu")
    keyboard.button(text="❓ COMO COMPRAR", callback_data="help_buy_capturas")
    keyboard.adjust(1)
    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode=ParseMode.MARKDOWN)

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

async def help_buy_capturas(callback: types.CallbackQuery):
    """
    Displays help instructions for buying Capturas.
    """
    help_text = (
        "📖 **Como comprar Capturas:**\n\n"
        "Envie um comando no seguinte formato para comprar:\n\n"
        "```\n/pokemart capturas 5 x3, 6 x1\n```\n"
        "Isso significa que você deseja comprar 3 unidades do card com ID 5 e 1 unidade do card com ID 6.\n\n"
        "Certifique-se de ter pokecoins suficientes para a compra."
    )
    await callback.answer(help_text, show_alert=True)

async def capturas_purchase_handler(message: types.Message):
    """
    Handles purchase orders for Capturas.
    Expected format:
      /pokemart capturas <ID xQuantidade, ...>
    """
    text = message.text.strip()
    parts = text.split(maxsplit=2)
    if len(parts) < 3 or parts[1].lower() != "capturas":
        raise SkipHandler()
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

    async with get_session() as session:
        total_cost = 0
        for card_id, quantity in orders:
            result = await session.execute(
                select(func.count()).select_from(
                    select(Marketplace)
                    .where(Marketplace.card_id == card_id)
                    .subquery()
                )
            )
            available = result.scalar() or 0
            if available < quantity:
                await message.reply(
                    f"❌ **Erro:** Listings insuficientes para o card ID `{card_id}`. Disponível: `{available}`.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            result = await session.execute(
                select(Marketplace)
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

    # Store purchase details for confirmation.
    pending_purchase[message.from_user.id] = orders

    confirm_text = "⚠️ **Confirmação de Compra**\n\nVocê está prestes a comprar:\n\n"
    for card_id, quantity in orders:
        async with get_session() as session:
            result = await session.execute(
                select(Marketplace)
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

async def confirm_buy(callback: types.CallbackQuery):
    """
    Processes confirmation for buying Capturas.
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
        for card_id, quantity in orders:
            result = await session.execute(
                select(Marketplace)
                .where(Marketplace.card_id == card_id)
                .limit(quantity)
            )
            listings = result.scalars().all()
            if len(listings) < quantity:
                await callback.answer(f"❌ Erro: Listings insuficientes para o card ID {card_id}.", show_alert=True)
                return
            for listing in listings:
                price = listing.price
                total_cost += price
                await session.delete(listing)
                result = await session.execute(
                    select(Inventory).where(Inventory.user_id == buyer_id, Inventory.card_id == card_id)
                )
                inv_item = result.scalar_one_or_none()
                if inv_item:
                    inv_item.quantity += 1
                else:
                    from database.models import Inventory
                    new_inv = Inventory(user_id=buyer_id, card_id=card_id, quantity=1)
                    session.add(new_inv)
        buyer.coins -= total_cost
        await session.commit()

    await callback.message.edit_text(
        f"✅ **Compra concluída!** Você gastou `{total_cost}` pokecoins e recebeu os cards comprados.",
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

# Import or define the router instance.
from aiogram import Router
router = Router()

# Register purchase order handler.
def register_handlers(router):
    router.message.register(capturas_purchase_handler, Command("pokemart"))
    router.callback_query.register(confirm_buy, lambda call: call.data.startswith("confirm_buy_"))
# Ensure the router is passed to the handler registration function.
register_handlers(router)
router.callback_query.register(capturas_page, lambda call: call.data.startswith("capturas_page_"))
router.callback_query.register(help_buy_capturas, lambda call: call.data == "help_buy_capturas")

register_handlers(router)
