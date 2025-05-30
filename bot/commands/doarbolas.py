from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from sqlalchemy.future import select
from database.models import User
from database.session import get_session

router = Router()

# Lista de grupos oficiais onde o comando pode ser usado
OFFICIAL_GROUPS = {
    "pokutrocas": -1002618854262,
    "pokutv": -1002618485697,
    "pokurandom": -1002535827033,
    "pokumusica": -1002640439235,
    "pokuasia": -1002582806902,
    "pokuanimagame": -1002521798243,
    "pokuginasio": -1002533762710
}

# Adiciona dicionário para rastrear doações pendentes
active_donations = {}

@router.message(Command("doarbolas"))
async def doarbolas_command(message: types.Message):
    """
    Handles the /doarbolas command for donating Pokébolas.
    Expected format: /doarbolas <quantity|*> <nickname>
    """
    # Verificar se o comando está sendo usado em um grupo oficial
    chat = message.chat
    if not chat.username or chat.username.lower() not in OFFICIAL_GROUPS:
        await message.reply(
            "❌ **Este comando só pode ser usado nos grupos oficiais:**\n\n"
            "☀️ GERAL @pokutrocas\n"
            "☀️ TV @pokutv\n"
            "☀️ RANDOM @pokurandom\n"
            "☀️ MÚSICA @pokumusica\n"
            "☀️ ÁSIA @pokuasia\n"
            "☀️ ANIMAGAME @pokuanimagame\n"
            "☀️ GINÁSIO @pokuginasio",
            parse_mode=ParseMode.MARKDOWN
        )
        return
        
    user_id = message.from_user.id

    # Verifica se já há um processo de doação em andamento
    if user_id in active_donations:
        await message.reply(
            "⚠️ Você já possui um processo de doação em andamento. Conclua ou cancele a transação atual antes de iniciar outra.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    text_parts = message.text.split(maxsplit=1)
    if len(text_parts) < 2:
        await message.reply(
            "❗ **Erro:** Especifique a quantidade de Pokébolas e o nickname do destinatário.\n"
            "Exemplos:\n"
            "• `/doarbolas 20 nickname`\n"
            "• `/doarbolas * nickname`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    args = text_parts[1].strip()
    parts = args.split()
    if len(parts) < 2:
        await message.reply(
            "❗ **Erro:** Especifique a quantidade de Pokébolas e o nickname do destinatário.\n"
            "Exemplos:\n"
            "• `/doarbolas 20 nickname`\n"
            "• `/doarbolas * nickname`",
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
        donation_quantity = donor.pokeballs
    else:
        try:
            donation_quantity = int(quantity)
        except ValueError:
            await message.reply(
                "❗ **Erro:** A quantidade deve ser um número inteiro válido ou `*` para doar tudo.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

    if donation_quantity <= 0 or donor.pokeballs < donation_quantity:
        await message.reply(
            f"❌ **Erro:** Você não tem Pokébolas suficientes para doar.\n"
            f"🎯 **Suas Pokébolas:** {donor.pokeballs}",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Após as validações iniciais, antes de enviar o botão de confirmação, marca o usuário
    active_donations[user_id] = True

    # Confirmation step.
    await message.reply(
        f"⚠️ **Confirmação:** Você está prestes a doar `{donation_quantity}` Pokébolas para `{nickname}`.\n"
        "Clique em **Confirmar** para continuar ou ignore esta mensagem para cancelar.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text="✅ Confirmar", callback_data=f"confirm_poke_{donation_quantity}_{nickname}")],
                [types.InlineKeyboardButton(text="❌ Cancelar", callback_data="cancel_donation")]
            ]
        )
    )

@router.callback_query(lambda call: call.data.startswith("confirm_poke_"))
async def confirm_poke_donation(callback: types.CallbackQuery):
    """
    Processes confirmation for a Pokébola donation.
    Expected callback_data: "confirm_poke_{quantity}_{nickname}"
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

    try:
        async with get_session() as session:
            # Fetch donor and recipient com uma única operação para evitar condições de corrida
            donor_result = await session.execute(select(User).where(User.id == donor_id))
            donor = donor_result.scalar_one_or_none()
            recipient_result = await session.execute(select(User).where(User.nickname == nickname))
            recipient = recipient_result.scalar_one_or_none()

            # Validações completas antes de qualquer modificação
            if not donor or not recipient:
                await callback.answer("Usuário não encontrado.", show_alert=True)
                return

            if donor.pokeballs < donation_quantity:
                await callback.answer("Você não tem pokébolas suficientes.", show_alert=True)
                return

            # Transferência atômica das pokebolas
            donor.pokeballs -= donation_quantity
            recipient.pokeballs += donation_quantity
            await session.commit()

        # Remove doação ativa após confirmação
        if donor_id in active_donations:
            del active_donations[donor_id]

        # Feedback para o usuário após operação bem-sucedida
        await callback.message.edit_text(
            f"✅ Doação concluída! Você doou {donation_quantity} pokébolas para {nickname}.",
            parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer("Doação realizada com sucesso!", show_alert=True)
        
    except Exception as e:
        # Tratamento de erro durante a transferência
        await callback.message.edit_text(
            "❌ **Erro:** Ocorreu um problema durante a doação. Tente novamente mais tarde.",
            parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer("Erro durante a doação.", show_alert=True)
        # Idealmente, aqui você faria log do erro para depuração

        if donor_id in active_donations:
            del active_donations[donor_id]

@router.callback_query(lambda call: call.data == "cancel_donation")
async def cancel_donation(callback: types.CallbackQuery):
    """
    Cancels any pending donation action.
    """
    # Remove o estado de doação pendente
    user_id = callback.from_user.id
    if user_id in active_donations:
        del active_donations[user_id]

    await callback.message.edit_text("❌ Doação cancelada.", parse_mode=ParseMode.MARKDOWN)
    await callback.answer("Doação cancelada.", show_alert=True)
