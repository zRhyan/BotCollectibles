from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload
from database.models import User, Inventory, Card
from database.session import get_session

router = Router()

# Temporary in-memory store for pending specific card donations.
# In production, consider a persistent or per‑user FSM approach.
pending_specific_donations = {}

@router.message(Command("doarcards"))
async def doarcards_command(message: types.Message):
    """
    Handles the /doarcard command for donating cards.
    Expected formats:
      • To donate all cards: /doarcard * <nickname>
      • To donate specific cards: /doarcard <card_id xQuantidade, ...> <nickname>
    """
    user_id = message.from_user.id
    text_parts = message.text.split(maxsplit=1)
    if len(text_parts) < 2:
        await message.reply(
            "❗ **Erro:** Especifique os cards que deseja doar e o nickname do destinatário.\n"
            "Exemplos:\n"
            "• `/doarcard * nickname` para doar todos os seus cards\n"
            "• `/doarcard 7 x3, 45 x2, 12 x5 nickname` para doar quantidades específicas.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    args = text_parts[1].strip()
    tokens = args.split()
    if not tokens:
        await message.reply("❗ **Erro:** Argumentos inválidos.", parse_mode=ParseMode.MARKDOWN)
        return

    if tokens[0] == "*":
        await handle_all_card_donation(args, message)
    else:
        await handle_specific_card_donation(args, message)


async def handle_all_card_donation(args: str, message: types.Message):
    """
    Processes donation of all cards.
    Expected format: "* <nickname>"
    """
    parts = args.split()
    if len(parts) < 2:
        await message.reply(
            "❗ **Erro:** Especifique o nickname do destinatário.\n"
            "Exemplo: `/doarcard * nickname`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    nickname = parts[1]

    # Verify recipient existence.
    async with get_session() as session:
        result = await session.execute(select(User).where(User.nickname == nickname))
        recipient = result.scalar_one_or_none()
    if not recipient:
        await message.reply(
            f"❌ **Erro:** Nenhum usuário encontrado com o nickname `{nickname}`.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Confirmation step.
    await message.reply(
        f"⚠️ **Confirmação:** Você está prestes a doar todos os seus cards para `{nickname}`.\n"
        "Clique em **Confirmar** para continuar ou ignore esta mensagem para cancelar.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text="✅ Confirmar", callback_data=f"confirm_card_all_{nickname}")],
                [types.InlineKeyboardButton(text="❌ Cancelar", callback_data="cancel_donation")]
            ]
        )
    )


async def handle_specific_card_donation(args: str, message: types.Message):
    """
    Processes donation of specific cards.
    Expected format: "<card_id xQuantidade, ...> <nickname>"
    Ex.: /doarcard 7 x3, 45 x2, 12 x5 nickname
    """
    parts = args.rsplit(maxsplit=1)
    if len(parts) < 2:
        await message.reply(
            "❗ **Erro:** Especifique os IDs dos cards, as quantidades e o nickname do destinatário.\n"
            "Exemplo: `/doarcard 7 x3, 45 x2, 12 x5 nickname`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    card_data = parts[0]
    nickname = parts[1]

    # Verify recipient existence.
    async with get_session() as session:
        result = await session.execute(select(User).where(User.nickname == nickname))
        recipient = result.scalar_one_or_none()
    if not recipient:
        await message.reply(
            f"❌ **Erro:** Nenhum usuário encontrado com o nickname `{nickname}`.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    donations = []
    for item in card_data.split(","):
        try:
            card_id_str, quantity_str = item.strip().split("x")
            card_id = int(card_id_str)
            quantity = int(quantity_str)
            donations.append((card_id, quantity))
        except ValueError:
            await message.reply(
                f"❌ **Erro:** Formato inválido para o item `{item}`. Use o formato `ID xQuantidade`.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

    # Store the donation details temporarily using the donor's id.
    pending_specific_donations[message.from_user.id] = donations

    donation_list = "\n".join([f"- Card ID `{card_id}`: `{quantity}` unidades" for card_id, quantity in donations])
    await message.reply(
        f"⚠️ **Confirmação:** Você está prestes a doar os seguintes cards para `{nickname}`:\n"
        f"{donation_list}\n\n"
        "Clique em **Confirmar** para continuar ou ignore esta mensagem para cancelar.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text="✅ Confirmar", callback_data=f"confirm_specific_{nickname}")],
                [types.InlineKeyboardButton(text="❌ Cancelar", callback_data="cancel_donation")]
            ]
        )
    )


@router.callback_query(lambda call: call.data.startswith("confirm_card_all_"))
async def confirm_card_all_donation(callback: types.CallbackQuery):
    """
    Processes confirmation for donating all cards.
    Callback data format: "confirm_card_all_{nickname}"
    """
    parts = callback.data.split("_")
    if len(parts) < 4:
        await callback.answer("Dados inválidos.", show_alert=True)
        return
    nickname = parts[3]
    donor_id = callback.from_user.id

    async with get_session() as session:
        donor_result = await session.execute(
            select(User).where(User.id == donor_id).options(joinedload(User.inventory))
        )
        donor = donor_result.unique().scalar_one_or_none()
        recipient_result = await session.execute(select(User).where(User.nickname == nickname))
        recipient = recipient_result.scalar_one_or_none()
        if not donor or not recipient:
            await callback.answer("Usuário não encontrado.", show_alert=True)
            return

        # Transfer all cards from donor to recipient.
        for inv_item in donor.inventory:
            card_id = inv_item.card_id
            rec_inv_result = await session.execute(
                select(Inventory).where(Inventory.user_id == recipient.id, Inventory.card_id == card_id)
            )
            recipient_inv = rec_inv_result.scalar_one_or_none()
            if recipient_inv:
                recipient_inv.quantity += inv_item.quantity
            else:
                new_inv = Inventory(user_id=recipient.id, card_id=card_id, quantity=inv_item.quantity)
                session.add(new_inv)
            inv_item.quantity = 0
        await session.commit()

    await callback.message.edit_text(
        f"✅ Doação concluída! Você doou todos os seus cards para {nickname}.",
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer("Doação realizada com sucesso!", show_alert=True)


@router.callback_query(lambda call: call.data.startswith("confirm_specific_"))
async def confirm_specific_donation(callback: types.CallbackQuery):
    """
    Processes confirmation for donating specific cards.
    Callback data format: "confirm_specific_{nickname}"
    Donation details are retrieved from the temporary store.
    """
    parts = callback.data.split("_")
    if len(parts) < 3:
        await callback.answer("Dados inválidos.", show_alert=True)
        return
    nickname = parts[2]
    donor_id = callback.from_user.id

    if donor_id not in pending_specific_donations:
        await callback.answer("Nenhuma doação pendente encontrada.", show_alert=True)
        return

    donations = pending_specific_donations.pop(donor_id)

    async with get_session() as session:
        donor_result = await session.execute(
            select(User).where(User.id == donor_id).options(joinedload(User.inventory))
        )
        donor = donor_result.unique().scalar_one_or_none()
        recipient_result = await session.execute(select(User).where(User.nickname == nickname))
        recipient = recipient_result.scalar_one_or_none()

        if not donor or not recipient:
            await callback.answer("Usuário não encontrado.", show_alert=True)
            return

        for card_id, quantity in donations:
            donor_inv = next((inv for inv in donor.inventory if inv.card_id == card_id), None)
            if not donor_inv or donor_inv.quantity < quantity:
                await callback.answer(f"Você não possui quantidade suficiente do card ID {card_id}.", show_alert=True)
                continue

            donor_inv.quantity -= quantity

            rec_inv_result = await session.execute(
                select(Inventory).where(Inventory.user_id == recipient.id, Inventory.card_id == card_id)
            )
            recipient_inv = rec_inv_result.scalar_one_or_none()
            if recipient_inv:
                recipient_inv.quantity += quantity
            else:
                new_inv = Inventory(user_id=recipient.id, card_id=card_id, quantity=quantity)
                session.add(new_inv)
        await session.commit()

    await callback.message.edit_text(
        f"✅ Doação concluída! Você doou os cards especificados para {nickname}.",
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer("Doação realizada com sucesso!", show_alert=True)


@router.callback_query(lambda call: call.data == "cancel_donation")
async def cancel_donation(callback: types.CallbackQuery):
    """
    Cancels any pending donation action.
    """
    await callback.message.edit_text("❌ Doação cancelada.", parse_mode=ParseMode.MARKDOWN)
    await callback.answer("Doação cancelada.", show_alert=True)
