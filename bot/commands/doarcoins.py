from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from sqlalchemy.future import select
from database.models import User
from database.session import get_session

router = Router()

@router.message(Command("doarcoins"))
async def doarcoins_command(message: types.Message):
    """
    Handles the /doarcoins command for donating Pokécoins.
    Expected format: /doarcoins <quantity|*> <nickname>
    """
    user_id = message.from_user.id
    text_parts = message.text.split(maxsplit=1)
    if len(text_parts) < 2:
        await message.reply(
            "❗ **Erro:** Especifique a quantidade de Pokecoins e o nickname do destinatário.\n"
            "Exemplos:\n"
            "• `/doarcoins 50 nickname`\n"
            "• `/doarcoins * nickname`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    args = text_parts[1].strip()
    parts = args.split()
    if len(parts) < 2:
        await message.reply(
            "❗ **Erro:** Especifique a quantidade de Pokecoins e o nickname do destinatário.\n"
            "Exemplos:\n"
            "• `/doarcoins 50 nickname`\n"
            "• `/doarcoins * nickname`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    quantity = parts[0]
    nickname = parts[1]

    # Fetch donor.
    async with get_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        donor = result.scalar_one_or_none()
    if not donor:
        await message.reply(
            "❌ **Erro:** Você ainda não está registrado no sistema. Use o comando `/jornada` para começar sua aventura.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Fetch recipient.
    async with get_session() as session:
        result = await session.execute(select(User).where(User.nickname == nickname))
        recipient = result.scalar_one_or_none()
    if not recipient:
        await message.reply(
            f"❌ **Erro:** Nenhum usuário encontrado com o nickname `{nickname}`.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Determine donation quantity.
    if quantity == "*":
        donation_quantity = donor.coins
    else:
        try:
            donation_quantity = int(quantity)
        except ValueError:
            await message.reply(
                "❗ **Erro:** A quantidade deve ser um número inteiro válido ou `*` para doar tudo.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

    if donation_quantity <= 0 or donor.coins < donation_quantity:
        await message.reply(
            f"❌ **Erro:** Você não tem Pokecoins suficientes para doar.\n"
            f"💰 **Suas Pokécoins:** {donor.coins}",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Confirmation step.
    await message.reply(
        f"⚠️ **Confirmação:** Você está prestes a doar `{donation_quantity}` Pokecoins para `{nickname}`.\n"
        "Clique em **Confirmar** para continuar ou ignore esta mensagem para cancelar.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text="✅ Confirmar", callback_data=f"confirm_coins_{donation_quantity}_{nickname}")],
                [types.InlineKeyboardButton(text="❌ Cancelar", callback_data="cancel_donation")]
            ]
        )
    )

@router.callback_query(lambda call: call.data.startswith("confirm_coins_"))
async def confirm_coins_donation(callback: types.CallbackQuery):
    """
    Processes confirmation for a Pokecoin donation.
    Expected callback_data: "confirm_coins_{quantity}_{nickname}"
    """
    parts = callback.data.split("_")
    if len(parts) < 4:
        await callback.answer("Dados inválidos.", show_alert=True)
        return
    try:
        donation_quantity = int(parts[2])
    except ValueError:
        await callback.answer("Quantidade inválida.", show_alert=True)
        return
    nickname = parts[3]
    donor_id = callback.from_user.id

    async with get_session() as session:
        # Fetch donor and recipient.
        donor_result = await session.execute(select(User).where(User.id == donor_id))
        donor = donor_result.scalar_one_or_none()
        recipient_result = await session.execute(select(User).where(User.nickname == nickname))
        recipient = recipient_result.scalar_one_or_none()

        if not donor or not recipient:
            await callback.answer("Usuário não encontrado.", show_alert=True)
            return

        if donor.coins < donation_quantity:
            await callback.answer("Você não tem Pokecoins suficientes.", show_alert=True)
            return

        donor.coins -= donation_quantity
        recipient.coins += donation_quantity
        await session.commit()

    await callback.message.edit_text(
        f"✅ Doação concluída! Você doou {donation_quantity} Pokecoins para {nickname}.",
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