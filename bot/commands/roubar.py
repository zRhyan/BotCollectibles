from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload
from database.models import User, Inventory
from database.session import get_session

router = Router()

# Temporary in-memory store for pending trades
pending_trades = {}

@router.message(Command("roubar"))
async def roubar_command(message: types.Message):
    """
    Handles the /roubar command for trading cards.
    Expected format:
    /roubar id1 xqty1, id2 xqty2 X id3 xqty3, id4 xqty4
    """
    user_id = message.from_user.id
    text_parts = message.text.split("X")
    if len(text_parts) != 2:
        await message.reply(
            "❗ **Erro:** Formato inválido. Use o formato:\n"
            "`/roubar id1 xqty1, id2 xqty2 X id3 xqty3, id4 xqty4`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    try:
        offered_cards = parse_card_data(text_parts[0].strip())
        requested_cards = parse_card_data(text_parts[1].strip())
    except ValueError as e:
        await message.reply(f"❗ **Erro:** {e}", parse_mode=ParseMode.MARKDOWN)
        return

    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.reply(
            "❗ **Erro:** Você deve responder à mensagem da pessoa com quem deseja trocar.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    target_user = message.reply_to_message.from_user

    # Verify both users exist in the database
    async with get_session() as session:
        donor = await session.get(User, user_id)
        recipient = await session.get(User, target_user.id)

        if not donor or not recipient:
            await message.reply(
                "❌ **Erro:** Um dos usuários não está registrado no sistema.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Check if the donor has enough cards to offer
        for card_id, qty in offered_cards:
            inv_item = await session.execute(
                select(Inventory).where(Inventory.user_id == user_id, Inventory.card_id == card_id)
            )
            inv_item = inv_item.scalar_one_or_none()
            if not inv_item or inv_item.quantity < qty:
                await message.reply(
                    f"❌ **Erro:** Você não possui `{qty}` unidades do card ID `{card_id}`.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

    # Store the trade details temporarily
    pending_trades[user_id] = {
        "offered": offered_cards,
        "requested": requested_cards,
        "recipient_id": target_user.id
    }

    # Send confirmation message to the recipient
    offered_text = format_card_list(offered_cards)
    requested_text = format_card_list(requested_cards)
    await message.reply_to_message.reply(
        f"⚠️ **Confirmação de Troca**\n\n"
        f"🔄 **Oferta de {message.from_user.username or 'Usuário'}:**\n{offered_text}\n\n"
        f"🎯 **Solicitação:**\n{requested_text}\n\n"
        "Clique em **Aceitar** para confirmar ou **Recusar** para cancelar.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text="✅ Aceitar", callback_data=f"accept_trade_{user_id}")],
                [types.InlineKeyboardButton(text="❌ Recusar", callback_data=f"reject_trade_{user_id}")]
            ]
        )
    )


@router.callback_query(lambda call: call.data.startswith("accept_trade_"))
async def accept_trade(callback: types.CallbackQuery):
    """
    Handles the acceptance of a trade.
    """
    donor_id = int(callback.data.split("_")[-1])
    recipient_id = callback.from_user.id

    if donor_id not in pending_trades or pending_trades[donor_id]["recipient_id"] != recipient_id:
        await callback.answer("Troca inválida ou expirada.", show_alert=True)
        return

    trade = pending_trades.pop(donor_id)

    async with get_session() as session:
        # Process the trade
        for card_id, qty in trade["offered"]:
            donor_inv = await session.execute(
                select(Inventory).where(Inventory.user_id == donor_id, Inventory.card_id == card_id)
            )
            donor_inv = donor_inv.scalar_one_or_none()
            donor_inv.quantity -= qty

            recipient_inv = await session.execute(
                select(Inventory).where(Inventory.user_id == recipient_id, Inventory.card_id == card_id)
            )
            recipient_inv = recipient_inv.scalar_one_or_none()
            if recipient_inv:
                recipient_inv.quantity += qty
            else:
                session.add(Inventory(user_id=recipient_id, card_id=card_id, quantity=qty))

        for card_id, qty in trade["requested"]:
            recipient_inv = await session.execute(
                select(Inventory).where(Inventory.user_id == recipient_id, Inventory.card_id == card_id)
            )
            recipient_inv = recipient_inv.scalar_one_or_none()
            recipient_inv.quantity -= qty

            donor_inv = await session.execute(
                select(Inventory).where(Inventory.user_id == donor_id, Inventory.card_id == card_id)
            )
            donor_inv = donor_inv.scalar_one_or_none()
            if donor_inv:
                donor_inv.quantity += qty
            else:
                session.add(Inventory(user_id=donor_id, card_id=card_id, quantity=qty))

        await session.commit()

    await callback.message.edit_text(
        "✅ **Troca concluída com sucesso!**",
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer("Troca realizada com sucesso!", show_alert=True)


@router.callback_query(lambda call: call.data.startswith("reject_trade_"))
async def reject_trade(callback: types.CallbackQuery):
    """
    Handles the rejection of a trade.
    """
    donor_id = int(callback.data.split("_")[-1])
    recipient_id = callback.from_user.id

    if donor_id not in pending_trades or pending_trades[donor_id]["recipient_id"] != recipient_id:
        await callback.answer("Troca inválida ou expirada.", show_alert=True)
        return

    pending_trades.pop(donor_id)
    await callback.message.edit_text("❌ **Troca recusada.**", parse_mode=ParseMode.MARKDOWN)
    await callback.answer("Troca recusada.", show_alert=True)


def parse_card_data(card_data: str):
    """
    Parses card data in the format "id1 xqty1, id2 xqty2".
    Returns a list of tuples [(id1, qty1), (id2, qty2)].
    """
    cards = []
    for item in card_data.split(","):
        try:
            card_id_str, qty_str = item.strip().split("x")
            card_id = int(card_id_str)
            qty = int(qty_str)
            cards.append((card_id, qty))
        except ValueError:
            raise ValueError(f"Formato inválido para `{item}`. Use `ID xQuantidade`.")
    return cards


def format_card_list(cards):
    """
    Formats a list of cards into a readable string.
    """
    return "\n".join([f"- Card ID `{card_id}`: `{qty}` unidades" for card_id, qty in cards])
