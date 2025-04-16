from aiogram import Router, types, F
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

class DoarCardsState(StatesGroup):
    """
    States for the /doarcards command, using the aiogram v3 FSM.
    """
    WAITING_CONFIRMATION = State()


@router.message(Command(commands=["doarcards"]))
async def doarcards_command(message: types.Message, state: FSMContext) -> None:
    """
    Entry point for the /doarcards command.

    Expected formats:
      - /doarcards * <nickname>
      - /doarcards <card_id xQuantidade, ...> <nickname>
        e.g. /doarcards 7 x3, 45 x2, 12 x5 nickname
    """
    text_parts = message.text.split(maxsplit=1)
    if len(text_parts) < 2:
        await message.reply(
            "❗ **Erro:** Especifique os cards que deseja doar e o nickname do destinatário.\n"
            "Exemplos:\n"
            "• `/doarcards * nickname` para doar todos os seus cards\n"
            "• `/doarcards 7 x3, 45 x2, 12 x5 nickname` para doar quantidades específicas.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    args = text_parts[1].strip()
    tokens = args.split()
    if not tokens:
        await message.reply("❗ **Erro:** Argumentos inválidos.", parse_mode=ParseMode.MARKDOWN)
        return

    donor_id = message.from_user.id

    # Check if user tries to donate all cards
    if tokens[0] == "*":
        # Format: /doarcards * <nickname>
        if len(tokens) < 2:
            await message.reply(
                "❗ **Erro:** Especifique o nickname do destinatário.\n"
                "Exemplo: `/doarcards * nickname`",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        nickname = tokens[1]
        donate_type = "all"

        # Verify the recipient
        async with get_session() as session:
            recipient_res = await session.execute(
                select(User).where(User.nickname == nickname)
            )
            recipient = recipient_res.scalar_one_or_none()

        if not recipient:
            await message.reply(
                f"❌ **Erro:** Nenhum usuário encontrado com o nickname `{nickname}`.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        if recipient.id == donor_id:
            await message.reply(
                "❗ Você não pode doar cards para si mesmo.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Save in FSM data
        await state.update_data(
            donate_type=donate_type,
            nickname=nickname
        )

        # Build confirmation message
        await message.reply(
            f"⚠️ **Confirmação:** Você está prestes a doar todos os seus cards para `{nickname}`.\n"
            "Clique em **Confirmar** para continuar ou ignore esta mensagem para cancelar.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="✅ Confirmar", callback_data="donation_confirm")
                    ],
                    [
                        InlineKeyboardButton(text="❌ Cancelar", callback_data="donation_cancel")
                    ]
                ]
            )
        )
        await state.set_state(DoarCardsState.WAITING_CONFIRMATION)

    else:
        # Format: /doarcards <card_id xQuant, ...> <nickname>
        parts = args.rsplit(maxsplit=1)
        if len(parts) < 2:
            await message.reply(
                "❗ **Erro:** Especifique os IDs dos cards, as quantidades e o nickname do destinatário.\n"
                "Exemplo: `/doarcards 7 x3, 45 x2, 12 x5 nickname`",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        card_data = parts[0]
        nickname = parts[1]
        donate_type = "specific"

        # Check if the recipient exists
        async with get_session() as session:
            recipient_res = await session.execute(
                select(User).where(User.nickname == nickname)
            )
            recipient = recipient_res.scalar_one_or_none()

        if not recipient:
            await message.reply(
                f"❌ **Erro:** Nenhum usuário encontrado com o nickname `{nickname}`.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        if recipient.id == donor_id:
            await message.reply(
                "❗ Você não pode doar cards para si mesmo.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        donations: list[tuple[int, int]] = []
        for item in card_data.split(","):
            try:
                card_id_str, quantity_str = item.strip().split("x")
                card_id = int(card_id_str)
                quantity = int(quantity_str)
                if quantity <= 0:
                    await message.reply(
                        f"❌ **Erro:** Quantidade inválida em `{item}`.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    return
                donations.append((card_id, quantity))
            except ValueError:
                await message.reply(
                    f"❌ **Erro:** Formato inválido para o item `{item}`. Use `ID xQuantidade`.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

        # Save in FSM
        await state.update_data(
            donate_type=donate_type,
            nickname=nickname,
            donations=donations
        )

        donation_list = "\n".join(
            [f"- Card ID `{card_id}`: `{quantity}` unidades" for card_id, quantity in donations]
        )
        await message.reply(
            f"⚠️ **Confirmação:** Você está prestes a doar os seguintes cards para `{nickname}`:\n"
            f"{donation_list}\n\n"
            "Clique em **Confirmar** para continuar ou ignore esta mensagem para cancelar.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="✅ Confirmar", callback_data="donation_confirm")
                    ],
                    [
                        InlineKeyboardButton(text="❌ Cancelar", callback_data="donation_cancel")
                    ]
                ]
            )
        )
        await state.set_state(DoarCardsState.WAITING_CONFIRMATION)


@router.callback_query(lambda call: call.data == "donation_confirm", DoarCardsState.WAITING_CONFIRMATION)
async def donation_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    """
    Handler for the "Confirm" inline button.
    We'll check which donation type the user selected ("all" or "specific"),
    retrieve the relevant data from FSM, then apply the transaction.
    """
    donor_id = callback.from_user.id
    data = await state.get_data()

    donate_type = data.get("donate_type")
    nickname = data.get("nickname")

    async with get_session() as session:
        donor_result = await session.execute(
            select(User).where(User.id == donor_id).options(joinedload(User.inventory))
        )
        donor = donor_result.unique().scalar_one_or_none()

        recipient_result = await session.execute(
            select(User).where(User.nickname == nickname)
        )
        recipient = recipient_result.scalar_one_or_none()

        if not donor or not recipient:
            await callback.answer("Usuário não encontrado.", show_alert=True)
            return

        if donor.id == recipient.id:
            await callback.answer("Você não pode doar cards para si mesmo.", show_alert=True)
            return

        if donate_type == "all":
            # Transfer all cards
            for inv_item in donor.inventory:
                if inv_item.quantity > 0:
                    rec_inv_result = await session.execute(
                        select(Inventory).where(
                            Inventory.user_id == recipient.id,
                            Inventory.card_id == inv_item.card_id
                        )
                    )
                    recipient_inv = rec_inv_result.scalar_one_or_none()
                    if recipient_inv:
                        recipient_inv.quantity += inv_item.quantity
                    else:
                        new_inv = Inventory(
                            user_id=recipient.id,
                            card_id=inv_item.card_id,
                            quantity=inv_item.quantity
                        )
                        session.add(new_inv)
                    inv_item.quantity = 0

            await session.commit()

            await callback.message.edit_text(
                f"✅ Doação concluída! Você doou todos os seus cards para {nickname}.",
                parse_mode=ParseMode.MARKDOWN
            )
            await callback.answer("Doação realizada com sucesso!", show_alert=True)
            await state.clear()

        elif donate_type == "specific":
            donations = data.get("donations", [])
            
            # Primeiro, verificamos se o usuário possui TODOS os cards necessários
            # antes de fazer qualquer alteração no banco de dados
            invalid_donations = []
            for card_id, quantity in donations:
                donor_inv = next((inv for inv in donor.inventory if inv.card_id == card_id), None)
                if not donor_inv or donor_inv.quantity < quantity:
                    invalid_donations.append((card_id, quantity))
            
            # Se houver algum card inválido, não realizamos nenhuma doação
            if invalid_donations:
                invalid_list = ", ".join([f"ID {card_id} (x{quantity})" 
                                        for card_id, quantity in invalid_donations])
                await callback.message.edit_text(
                    f"❌ **Doação cancelada!** Você não possui quantidade suficiente dos seguintes cards:\n"
                    f"`{invalid_list}`",
                    parse_mode=ParseMode.MARKDOWN
                )
                await callback.answer("Doação cancelada: cards insuficientes", show_alert=True)
                await state.clear()
                return
            
            # Somente prossegue com a doação se todos os cards forem válidos
            for card_id, quantity in donations:
                donor_inv = next((inv for inv in donor.inventory if inv.card_id == card_id), None)
                # A este ponto sabemos que o donor_inv existe e tem quantidade suficiente
                donor_inv.quantity -= quantity

                rec_inv_result = await session.execute(
                    select(Inventory).where(
                        Inventory.user_id == recipient.id,
                        Inventory.card_id == card_id
                    )
                )
                recipient_inv = rec_inv_result.scalar_one_or_none()
                if recipient_inv:
                    recipient_inv.quantity += quantity
                else:
                    new_inv = Inventory(
                        user_id=recipient.id,
                        card_id=card_id,
                        quantity=quantity
                    )
                    session.add(new_inv)

            # Confirma todas as alterações apenas se todas as validações passaram
            await session.commit()

            await callback.message.edit_text(
                f"✅ Doação concluída! Você doou os cards especificados para {nickname}.",
                parse_mode=ParseMode.MARKDOWN
            )
            await callback.answer("Doação realizada com sucesso!", show_alert=True)
            await state.clear()

        else:
            await callback.answer("Dados da doação ausentes.", show_alert=True)


@router.callback_query(lambda call: call.data == "donation_cancel", DoarCardsState.WAITING_CONFIRMATION)
async def donation_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    """
    Cancels any pending donation action.
    """
    await callback.message.edit_text("❌ Doação cancelada.", parse_mode=ParseMode.MARKDOWN)
    await callback.answer("Doação cancelada.", show_alert=True)
    await state.clear()
