from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload
import logging

from database.models import User, Inventory, Card, Marketplace
from database.session import get_session

router = Router()

# Temporary in-memory store for pending card sales, keyed by user ID
pending_sales = {}

@router.message(Command("venderc"))
async def venderc_command(message: types.Message):
    """
    Handles /venderc <card_id xQty, card_id xQty, ...>.
    Builds a confirmation inline keyboard with total value.
    """
    logging.info(f"[venderc_command] User {message.from_user.id} typed: {message.text}")

    user_id = message.from_user.id
    text_parts = message.text.split(maxsplit=1)

    if len(text_parts) < 2:
        logging.warning("[venderc_command] No card data provided after /venderc.")
        await message.reply(
            "❗ **Erro:** Você precisa especificar os IDs dos cards e as quantidades para vender.\n"
            "Exemplo:\n"
            "`/venderc 5 x2, 4 x1, 3 x10`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    args = text_parts[1].strip()
    card_data = args.split(",")

    # Parse card data
    cards_to_sell = []
    for item in card_data:
        try:
            card_id_str, quantity_str = item.strip().split("x")
            card_id = int(card_id_str)
            quantity = int(quantity_str)
            cards_to_sell.append((card_id, quantity))
        except ValueError:
            logging.warning(f"[venderc_command] Invalid format for item: {item}")
            await message.reply(
                f"❌ **Erro:** Formato inválido para o item `{item}`. Use o formato `ID xQuantidade`.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

    # Try to fetch user and build confirmation
    try:
        async with get_session() as session:
            # Find user
            user = (await session.execute(
                select(User).where(User.id == user_id)
            )).scalar_one_or_none()

            if not user:
                logging.warning(f"[venderc_command] User {user_id} not found in DB.")
                await message.reply(
                    "❌ **Erro:** Você ainda não está registrado no sistema. Use o comando `/jornada` para começar sua aventura.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

            # Load inventory
            result = await session.execute(
                select(Inventory).options(joinedload(Inventory.card))
                .where(Inventory.user_id == user_id)
            )
            inventory = result.scalars().all()
            inventory_dict = {inv.card_id: inv for inv in inventory}

            # Calculate total value
            total_value = 0
            confirmation_text = "⚠️ **Confirmação de Venda**\n\nVocê está prestes a vender:\n\n"

            for card_id, quantity in cards_to_sell:
                inv_item = inventory_dict.get(card_id)
                if not inv_item or inv_item.quantity < quantity:
                    logging.warning(
                        f"[venderc_command] User {user_id} doesn't have enough of card_id {card_id}."
                    )
                    await message.reply(
                        f"❌ **Erro:** Você não possui `{quantity}` unidades do card ID `{card_id}`.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    return

                # Calculate value based on rarity
                rarity_value = {"🥇": 1000, "🥈": 500, "🥉": 250}
                card_value = rarity_value.get(inv_item.card.rarity, 0) * quantity
                total_value += card_value

                confirmation_text += (
                    f"{inv_item.card.rarity} **{inv_item.card.id}. {inv_item.card.name}** "
                    f"- `{quantity}` unidades\n"
                    f"💰 Valor parcial: `{card_value}` pokecoins\n\n"
                )

            confirmation_text += (
                f"💵 **Total a receber:** `{total_value}` pokecoins\n\n"
                f"Deseja confirmar a venda?"
            )

            # Store sale details
            pending_sales[user_id] = cards_to_sell

            # Inline keyboard for confirm/cancel
            kb = InlineKeyboardBuilder()
            kb.button(text="✅ Vender", callback_data=f"confirm_sell_{user_id}")
            kb.button(text="❌ Cancelar", callback_data="cancel_sell")
            kb.adjust(1)

            logging.info(f"[venderc_command] Built confirmation for user {user_id}, total={total_value}")
            await message.reply(
                confirmation_text,
                reply_markup=kb.as_markup(),
                parse_mode=ParseMode.MARKDOWN
            )
    except Exception as e:
        logging.error(f"[venderc_command] Unexpected error: {e}", exc_info=True)
        await message.reply(
            f"❌ **Erro inesperado** ao processar /venderc: {e}",
            parse_mode=ParseMode.MARKDOWN
        )

@router.callback_query(lambda call: call.data.startswith("confirm_sell_"))
async def confirm_sell(callback: types.CallbackQuery):
    """
    After user confirms the sale, remove the items from inventory and create marketplace listings.
    """
    try:
        user_id = int(callback.data.split("_")[2])
    except (IndexError, ValueError):
        await callback.answer("Dados inválidos.", show_alert=True)
        return

    if user_id not in pending_sales:
        await callback.answer("Nenhuma venda pendente encontrada.", show_alert=True)
        return

    cards_to_sell = pending_sales.pop(user_id)

    try:
        async with get_session() as session:
            user = (await session.execute(
                select(User).where(User.id == user_id)
            )).scalar_one_or_none()

            if not user:
                await callback.answer("❌ Usuário não encontrado.", show_alert=True)
                return

            # Re-load user inventory
            inv_result = await session.execute(
                select(Inventory).options(joinedload(Inventory.card))
                .where(Inventory.user_id == user_id)
            )
            inventory = inv_result.scalars().all()
            inv_dict = {i.card_id: i for i in inventory}

            total_value = 0
            for card_id, quantity in cards_to_sell:
                inv_item = inv_dict.get(card_id)
                if not inv_item or inv_item.quantity < quantity:
                    await callback.answer("❌ Quantidade insuficiente para venda.", show_alert=True)
                    return

                card = inv_item.card
                rarity_value = {"🥇": 1000, "🥈": 500, "🥉": 250}
                card_value = rarity_value.get(card.rarity, 0) * quantity
                total_value += card_value

                inv_item.quantity -= quantity
                if inv_item.quantity <= 0:
                    await session.delete(inv_item)

                new_listing = Marketplace(
                    seller_id=user_id,
                    card_id=card_id,
                    price=rarity_value.get(card.rarity, 0)
                )
                session.add(new_listing)

            user.coins += total_value
            await session.commit()

        await callback.message.edit_text(
            f"✅ **Venda concluída!** Você recebeu `{total_value}` pokecoins.\n"
            "Os cards agora estão disponíveis no Pokémart.",
            parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer("Venda realizada com sucesso!", show_alert=True)

    except Exception as e:
        logging.error(f"[confirm_sell] Unexpected error: {e}", exc_info=True)
        await callback.answer(f"Erro inesperado: {e}", show_alert=True)

@router.callback_query(lambda call: call.data == "cancel_sell")
async def cancel_sell(callback: types.CallbackQuery):
    """
    Cancels any pending sale action.
    """
    user_id = callback.from_user.id
    if user_id in pending_sales:
        pending_sales.pop(user_id)
    await callback.message.edit_text("❌ Venda cancelada.", parse_mode=ParseMode.MARKDOWN)
    await callback.answer("Venda cancelada.", show_alert=True)
