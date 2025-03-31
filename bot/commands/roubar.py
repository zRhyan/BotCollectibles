from aiogram import Router, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from database.models import User, Inventory
from database.session import get_session

router = Router()

class RoubarState(StatesGroup):
    """
    States for the /roubar command.
    """
    WAITING_CONFIRMATION = State()


@router.message(Command(commands=["roubar"]))
async def roubar_command(message: types.Message, state: FSMContext) -> None:
    """
    Handles the /roubar command for exchanging ("trading") cards between two users.

    Expected format:
        /roubar <ID do outro usuário> id1 xqty1, id2 xqty2 X id3 xqty3, id4 xqty4
    Or if the user is replying to a target user's message:
        /roubar id1 xqty1, id2 xqty2 X id3 xqty3, id4 xqty4  (and we gather the user from the replied message)
    """
    donor_id = message.from_user.id

    # Attempt to parse the text for the user ID argument
    # We'll split on whitespace once to see if the first token is numeric
    text_parts = message.text.strip().split(maxsplit=1)

    if len(text_parts) < 2:
        await message.reply(
            "❗ **Erro:** Use o formato `/roubar <userid> <suas cartas> X <cartas alvo>` ou responda a mensagem do usuário alvo.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # If the user typed: /roubar <something>
    possible_user_arg = text_parts[1].split()[0]  # first token after /roubar
    remainder = None
    target_id = None

    if possible_user_arg.isdigit():
        # The user provided a numeric ID directly
        target_id = int(possible_user_arg)
        # The rest is after removing that token
        remainder_tokens = text_parts[1].split(maxsplit=1)
        if len(remainder_tokens) < 2:
            await message.reply(
                "❗ **Erro:** Faltam os dados de cartas. Exemplo: `/roubar 123 7 x2, 9 x1 X 10 x3, 11 x4`",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        remainder = remainder_tokens[1]
    else:
        # No numeric user ID => might rely on reply_to_message or we assume the entire text is the card data
        remainder = text_parts[1]

    # If still no target_id, we check if user replied to a message
    if not target_id:
        if message.reply_to_message and message.reply_to_message.from_user:
            target_id = message.reply_to_message.from_user.id
        else:
            await message.reply(
                "❗ **Erro:** Você deve informar o ID do usuário ou responder à mensagem do alvo.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

    # Now, parse remainder for the cards => must contain an 'X'
    if "X" not in remainder:
        await message.reply(
            "❗ **Erro:** Formato inválido. Use algo como: `id1 xqty1, id2 xqty2 X id3 xqty3, id4 xqty4`.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    text_cards_parts = remainder.split("X")
    if len(text_cards_parts) != 2:
        await message.reply(
            "❗ **Erro:** Formato inválido. Use o formato: `/roubar <userid> id1 xqty1, id2 xqty2 X id3 xqty3, id4 xqty4`.\n" 
            "Ou responda a mensagem do usuário alvo e use: `/roubar id1 xqty1, id2 xqty2 X id3 xqty3, id4 xqty4`.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    offered_str = text_cards_parts[0].strip()
    requested_str = text_cards_parts[1].strip()

    # Parse the card data
    try:
        offered_cards = parse_card_data(offered_str)
        requested_cards = parse_card_data(requested_str)
    except ValueError as e:
        await message.reply(f"❗ **Erro:** {e}", parse_mode=ParseMode.MARKDOWN)
        return

    # We'll verify that donor has enough for the offered cards
    # We'll also check if the target user has enough for the requested cards.
    # Actually, let's do that after the user confirms it. Or we can do partial check now.

    async with get_session() as session:
        donor = await session.get(User, donor_id)
        recipient = await session.get(User, target_id)

        if not donor or not recipient:
            await message.reply(
                "❌ **Erro:** Um dos usuários não está registrado no sistema.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

    # Store the trade info in FSM data
    await state.update_data(
        donor_id=donor_id,
        recipient_id=target_id,
        offered=offered_cards,
        requested=requested_cards
    )

    offered_text = format_card_list(offered_cards)
    requested_text = format_card_list(requested_cards)

    # We'll direct the user (the target) to click accept or reject.
    # But we actually need to send them a message they can see. Possibly we do a normal message from the donor.

    confirm_text = (
        f"⚠️ **Confirmação de Troca**\n\n"
        f"🔄 **Oferta de {message.from_user.username or donor_id}:**\n" + offered_text + "\n\n"
        f"🎯 **Solicitação:**\n" + requested_text + "\n\n"
        "Clique em **Aceitar** para confirmar ou **Recusar** para cancelar."
    )

    # The user might want to see it in the same chat
    # If the target user is in this group, they can see it.
    # We'll just do a normal reply in the same chat.

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Aceitar", callback_data="trade_accept"),
                InlineKeyboardButton(text="❌ Recusar", callback_data="trade_reject")
            ]
        ]
    )

    await message.reply(
        confirm_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb
    )

    await state.set_state(RoubarState.WAITING_CONFIRMATION)


@router.callback_query(lambda c: c.data == "trade_accept", RoubarState.WAITING_CONFIRMATION)
async def accept_trade(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    donor_id = data.get("donor_id")
    recipient_id = data.get("recipient_id")
    offered = data.get("offered", [])
    requested = data.get("requested", [])

    # The user who clicked accept must be the recipient
    if callback.from_user.id != recipient_id:
        await callback.answer("Você não é o usuário alvo dessa troca.", show_alert=True)
        return

    # Now we do the checks and transfer
    async with get_session() as session:
        # Donor must have all offered cards
        # Recipient must have all requested cards
        # We'll assume they're valid. If we want to check, do it now.
        donor_res = await session.execute(
            select(User).where(User.id == donor_id).options(joinedload(User.inventory))
        )
        donor = donor_res.unique().scalar_one_or_none()

        recipient_res = await session.execute(
            select(User).where(User.id == recipient_id).options(joinedload(User.inventory))
        )
        recipient = recipient_res.unique().scalar_one_or_none()

        if not donor or not recipient:
            await callback.answer("Um dos usuários não está registrado.", show_alert=True)
            return

        # Check donor's offered cards
        for card_id, qty in offered:
            donor_inv = next((inv for inv in donor.inventory if inv.card_id == card_id), None)
            if not donor_inv or donor_inv.quantity < qty:
                await callback.answer(
                    f"O doador não possui {qty}x do card ID {card_id}.", show_alert=True
                )
                return

        # Check recipient's requested cards
        for card_id, qty in requested:
            recip_inv = next((inv for inv in recipient.inventory if inv.card_id == card_id), None)
            if not recip_inv or recip_inv.quantity < qty:
                await callback.answer(
                    f"Você não possui {qty}x do card ID {card_id}.", show_alert=True
                )
                return

        # If all good, do the actual trade
        # Transfer from donor -> recipient
        for card_id, qty in offered:
            donor_inv = next((inv for inv in donor.inventory if inv.card_id == card_id), None)
            donor_inv.quantity -= qty
            recip_inv = next((inv for inv in recipient.inventory if inv.card_id == card_id), None)
            if recip_inv:
                recip_inv.quantity += qty
            else:
                session.add(Inventory(user_id=recipient_id, card_id=card_id, quantity=qty))

        # Transfer from recipient -> donor
        for card_id, qty in requested:
            recip_inv = next((inv for inv in recipient.inventory if inv.card_id == card_id), None)
            recip_inv.quantity -= qty
            donor_inv = next((inv for inv in donor.inventory if inv.card_id == card_id), None)
            if donor_inv:
                donor_inv.quantity += qty
            else:
                session.add(Inventory(user_id=donor_id, card_id=card_id, quantity=qty))

        await session.commit()

    await callback.message.edit_text("✅ **Troca concluída com sucesso!**", parse_mode=ParseMode.MARKDOWN)
    await callback.answer("Troca realizada com sucesso!", show_alert=True)
    await state.clear()


@router.callback_query(lambda c: c.data == "trade_reject", RoubarState.WAITING_CONFIRMATION)
async def reject_trade(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    recipient_id = data.get("recipient_id")

    # Only the recipient can reject
    if callback.from_user.id != recipient_id:
        await callback.answer("Você não é o usuário alvo dessa troca.", show_alert=True)
        return

    await callback.message.edit_text("❌ **Troca recusada.**", parse_mode=ParseMode.MARKDOWN)
    await callback.answer("Troca recusada.", show_alert=True)
    await state.clear()


def parse_card_data(card_data: str) -> list[tuple[int, int]]:
    """
    Parses card data in the format "id1 xqty1, id2 xqty2".
    Returns a list of tuples [(id1, qty1), (id2, qty2)].
    """
    cards = []
    for item in card_data.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            card_id_str, qty_str = item.split("x")
            card_id = int(card_id_str)
            qty = int(qty_str)
            if qty <= 0:
                raise ValueError(f"Quantidade inválida em `{item}`.")
            cards.append((card_id, qty))
        except ValueError:
            raise ValueError(f"Formato inválido para `{item}`. Use `ID xQuantidade`.")
    return cards


def format_card_list(cards: list[tuple[int,int]]) -> str:
    """
    Formats a list of cards into a readable string.
    """
    lines = [f"- Card ID `{cid}`: `{q}` unidades" for cid, q in cards]
    return "\n".join(lines)
