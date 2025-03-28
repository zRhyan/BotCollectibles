# commands/venderc.py

import logging
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload

from database.session import get_session
from database.models import User, Inventory, Card, Marketplace

# Configure logging
logging.basicConfig(level=logging.INFO)

# In-memory dictionary for pending sales { user_id: [(card_id, qty), ...] }
pending_sales = {}

# Initialize router
router = Router()

@router.message(Command("venderc"))
async def venderc_command(message: types.Message):
    """Handle the /venderc command to sell cards from the user's inventory."""
    logging.info("[DEBUG] ENTER: /venderc handler")
    try:
        # Test response to confirm handler is reached
        await message.reply("Comando /venderc recebido! Processando...")

        user_id = message.from_user.id
        text_parts = message.text.split(maxsplit=1)

        # Check if arguments are provided
        if len(text_parts) < 2:
            logging.info("[DEBUG] No arguments provided")
            await message.reply(
                "❗ **Erro:** Você precisa especificar os IDs dos cards e as quantidades para vender.\n"
                "Exemplo:\n"
                "`/venderc 5 x2, 4 x1, 3 x10`",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        args = text_parts[1].strip()
        logging.info(f"[DEBUG] Arguments: {args}")

        # Parse items in format "ID xQty"
        card_data = args.split(",")
        cards_to_sell = []
        for item in card_data:
            try:
                card_id_str, quantity_str = item.strip().split("x")
                card_id = int(card_id_str)
                qty = int(quantity_str)
                cards_to_sell.append((card_id, qty))
            except ValueError:
                logging.info(f"[DEBUG] Invalid format: {item}")
                await message.reply(
                    f"❌ **Erro:** Formato inválido para `{item}`. Use `ID xQuantidade`.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

        logging.info("[DEBUG] Starting database query")
        async with get_session() as session:
            logging.info("[DEBUG] Database session opened")
            # Fetch user
            user = (await session.execute(
                select(User).where(User.id == user_id)
            )).scalar_one_or_none()

            if not user:
                logging.info("[DEBUG] User not found in database")
                await message.reply(
                    "❌ **Erro:** Você ainda não está registrado. Use `/jornada`.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

            # Load user's inventory
            logging.info("[DEBUG] Querying user inventory")
            inv_result = await session.execute(
                select(Inventory).options(joinedload(Inventory.card))
                .where(Inventory.user_id == user_id)
            )
            user_inventory = inv_result.scalars().all()
            inv_dict = {inv.card_id: inv for inv in user_inventory}

            total_value = 0
            confirmation_text = "⚠️ **Confirmação de Venda**\n\nVocê está prestes a vender:\n\n"

            # Rarity value mapping
            rarity_value = {"🥇": 1000, "🥈": 500, "🥉": 250}

            # Validate and calculate sale
            for (card_id, qty) in cards_to_sell:
                inv_item = inv_dict.get(card_id)
                if not inv_item or inv_item.quantity < qty:
                    logging.info(f"[DEBUG] Insufficient quantity for card {card_id}")
                    await message.reply(
                        f"❌ **Erro:** Você não possui `{qty}` unidades do card ID `{card_id}`.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    return

                card = inv_item.card
                card_val = rarity_value.get(card.rarity, 0) * qty
                total_value += card_val

                confirmation_text += (
                    f"{card.rarity} **{card.id}. {card.name}** - `{qty}` unidades\n"
                    f"💰 Valor parcial: `{card_val}` pokecoins\n\n"
                )

            confirmation_text += f"💵 **Total a receber:** `{total_value}` pokecoins\n\n"
            confirmation_text += "Deseja confirmar a venda?"

            # Store pending sale
            pending_sales[user_id] = cards_to_sell
            logging.info(f"[DEBUG] Pending sale stored for user {user_id}")

            # Build confirmation keyboard
            kb = InlineKeyboardBuilder()
            kb.button(text="✅ Vender", callback_data=f"confirm_sell_{user_id}")
            kb.button(text="❌ Cancelar", callback_data="cancel_sell")
            kb.adjust(1)

            await message.reply(
                confirmation_text,
                reply_markup=kb.as_markup(),
                parse_mode=ParseMode.MARKDOWN
            )
            logging.info("[DEBUG] Confirmation message sent")

    except Exception as e:
        logging.error(f"[ERROR] Unhandled exception in /venderc: {e}", exc_info=True)
        await message.reply(
            "❌ **Erro inesperado.** Tente novamente mais tarde.",
            parse_mode=ParseMode.MARKDOWN
        )

@router.callback_query(lambda call: call.data.startswith("confirm_sell_"))
async def confirm_sell(callback: types.CallbackQuery):
    """Handle the confirmation of the card sale."""
    logging.info("[DEBUG] ENTER: confirm_sell callback")
    data_parts = callback.data.split("_")
    if len(data_parts) < 3:
        logging.info("[DEBUG] Invalid callback data")
        await callback.answer("Dados inválidos.", show_alert=True)
        return

    try:
        user_id = int(data_parts[2])
    except ValueError:
        logging.info("[DEBUG] Invalid user_id in callback data")
        await callback.answer("Dados inválidos.", show_alert=True)
        return

    if user_id not in pending_sales:
        logging.info("[DEBUG] No pending sales for user")
        await callback.answer("Nenhuma venda pendente encontrada.", show_alert=True)
        return

    cards_to_sell = pending_sales.pop(user_id)
    logging.info(f"[DEBUG] Confirming sale for user {user_id}, cards: {cards_to_sell}")

    try:
        async with get_session() as session:
            logging.info("[DEBUG] Database session opened for confirm_sell")
            # Fetch user
            user = (await session.execute(
                select(User).where(User.id == user_id)
            )).scalar_one_or_none()

            if not user:
                logging.info("[DEBUG] User not found in database")
                await callback.answer("Usuário não encontrado.", show_alert=True)
                return

            # Load inventory
            logging.info("[DEBUG] Querying user inventory for confirm_sell")
            inv_result = await session.execute(
                select(Inventory).options(joinedload(Inventory.card))
                .where(Inventory.user_id == user_id)
            )
            inv_list = inv_result.scalars().all()
            inv_dict = {i.card_id: i for i in inv_list}

            total_value = 0
            rarity_value = {"🥇": 1000, "🥈": 500, "🥉": 250}

            # Process the sale
            for (card_id, qty) in cards_to_sell:
                if card_id not in inv_dict or inv_dict[card_id].quantity < qty:
                    logging.info(f"[DEBUG] Insufficient quantity for card {card_id}")
                    await callback.answer("❌ Quantidade insuficiente para venda.", show_alert=True)
                    return

                card = inv_dict[card_id].card
                card_val = rarity_value.get(card.rarity, 0) * qty
                total_value += card_val

                # Update inventory
                inv_dict[card_id].quantity -= qty
                if inv_dict[card_id].quantity <= 0:
                    await session.delete(inv_dict[card_id])

                # Add to marketplace
                new_listing = Marketplace(
                    seller_id=user_id,
                    card_id=card_id,
                    price=rarity_value.get(card.rarity, 0)
                )
                session.add(new_listing)

            # Update user's coins
            user.coins += total_value
            await session.commit()

        logging.info(f"[DEBUG] Sale confirmed, user {user_id} earned {total_value} pokecoins")
        await callback.message.edit_text(
            f"✅ **Venda concluída!** Você recebeu `{total_value}` pokecoins.\n"
            "Os cards agora estão disponíveis no Pokémart.",
            parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer("Venda realizada com sucesso!", show_alert=True)

    except Exception as e:
        logging.error(f"[ERROR] Unhandled exception in confirm_sell: {e}", exc_info=True)
        await callback.answer(f"Erro inesperado => {e}", show_alert=True)

@router.callback_query(lambda call: call.data == "cancel_sell")
async def cancel_sell(callback: types.CallbackQuery):
    """Handle the cancellation of a pending sale."""
    logging.info("[DEBUG] ENTER: cancel_sell callback")
    user_id = callback.from_user.id
    if user_id in pending_sales:
        pending_sales.pop(user_id)
        logging.info(f"[DEBUG] Pending sale canceled for user {user_id}")

    await callback.message.edit_text("❌ Venda cancelada.", parse_mode=ParseMode.MARKDOWN)
    await callback.answer("Venda cancelada.", show_alert=True)