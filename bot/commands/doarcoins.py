from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from sqlalchemy.future import select
from database.models import User
from database.session import get_session
import logging
import time

# Configure logger
logger = logging.getLogger(__name__)

router = Router()

# Dicionário para rastrear transações pendentes
active_coin_donations = {}

# Tempo máximo (em segundos) que uma transação pode ficar pendente
TRANSACTION_TIMEOUT = 180  # 3 minutos

@router.message(Command("doarcoins"))
async def doarcoins_command(message: types.Message):
    """
    Handles the /doarcoins command for donating Pokecoins.
    Expected format: /doarcoins <quantity|*> <nickname>
    """
    user_id = message.from_user.id
    current_time = time.time()
    
    # Limpar doações antigas antes de verificar
    cleanup_pending_transactions()
    
    # Verificar se o usuário já está em processo de doação
    if user_id in active_coin_donations:
        await message.reply(
            "⚠️ **Você já tem um processo de doação em andamento!**\n"
            "Complete sua doação atual ou aguarde alguns minutos antes de tentar novamente.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
        
    # Registrar a transação pendente
    active_coin_donations[user_id] = current_time
    
    try:
        text_parts = message.text.split(maxsplit=1)
        if len(text_parts) < 2:
            if user_id in active_coin_donations:
                del active_coin_donations[user_id]
            await message.reply(
                "❗ **Erro:** Especifique a quantidade de Pokecoins e o nickname do destinatário.\n"
                "Exemplos:\n"
                "• `/doarcoins 100 nickname`\n"
                "• `/doarcoins * nickname`",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        args = text_parts[1].strip()
        parts = args.split()
        if len(parts) < 2:
            if user_id in active_coin_donations:
                del active_coin_donations[user_id]
            await message.reply(
                "❗ **Erro:** Especifique a quantidade de Pokecoins e o nickname do destinatário.\n"
                "Exemplos:\n"
                "• `/doarcoins 100 nickname`\n"
                "• `/doarcoins * nickname`",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        quantity = parts[0]
        nickname = parts[1]

        # Fetch donor and recipient in separate sessions to avoid transaction issues
        donor = None
        recipient = None
        
        # Get donor
        try:
            async with get_session() as session:
                result = await session.execute(select(User).where(User.id == user_id))
                donor = result.scalar_one_or_none()
                
            if not donor:
                if user_id in active_coin_donations:
                    del active_coin_donations[user_id]
                await message.reply(
                    "❌ **Erro:** Você ainda não está registrado no sistema. Use o comando `/jornada` para começar sua aventura.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
        except Exception as e:
            logger.error(f"Erro ao obter dados do doador: {str(e)}")
            if user_id in active_coin_donations:
                del active_coin_donations[user_id]
            await message.reply(
                "❌ **Erro ao verificar seu registro.** Por favor, tente novamente mais tarde.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
            
        # Get recipient
        try:
            async with get_session() as session:
                result = await session.execute(select(User).where(User.nickname == nickname))
                recipient = result.scalar_one_or_none()
                
            if not recipient:
                if user_id in active_coin_donations:
                    del active_coin_donations[user_id]
                await message.reply(
                    f"❌ **Erro:** Nenhum usuário encontrado com o nickname `{nickname}`.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
        except Exception as e:
            logger.error(f"Erro ao obter dados do destinatário: {str(e)}")
            if user_id in active_coin_donations:
                del active_coin_donations[user_id]
            await message.reply(
                "❌ **Erro ao verificar o destinatário.** Por favor, tente novamente mais tarde.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Determine donation quantity
        if quantity == "*":
            donation_quantity = donor.coins
        else:
            try:
                donation_quantity = int(quantity)
            except ValueError:
                if user_id in active_coin_donations:
                    del active_coin_donations[user_id]
                await message.reply(
                    "❗ **Erro:** A quantidade deve ser um número inteiro válido ou `*` para doar tudo.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

        if donation_quantity <= 0 or donor.coins < donation_quantity:
            if user_id in active_coin_donations:
                del active_coin_donations[user_id]
            await message.reply(
                f"❌ **Erro:** Você não tem Pokecoins suficientes para doar.\n"
                f"💰 **Suas Pokecoins:** {donor.coins}",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Confirmation step
        await message.reply(
            f"⚠️ **Confirmação:** Você está prestes a doar `{donation_quantity}` Pokecoins para `{nickname}`.\n"
            "Clique em **Confirmar** para continuar ou ignore esta mensagem para cancelar.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [types.InlineKeyboardButton(text="✅ Confirmar", callback_data=f"confirm_coin_{donation_quantity}_{nickname}")],
                    [types.InlineKeyboardButton(text="❌ Cancelar", callback_data="cancel_coin_donation")]
                ]
            )
        )
    except Exception as e:
        logger.error(f"Erro inesperado em doarcoins: {str(e)}", exc_info=True)
        if user_id in active_coin_donations:
            del active_coin_donations[user_id]
        await message.reply(
            "❌ **Erro:** Ocorreu um problema ao processar seu comando.",
            parse_mode=ParseMode.MARKDOWN
        )

@router.callback_query(lambda call: call.data.startswith("confirm_coin_"))
async def confirm_coin_donation(callback: types.CallbackQuery):
    """
    Processes confirmation for a Pokecoin donation.
    """
    user_id = callback.from_user.id
    try:
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

        try:
            async with get_session() as session:
                async with session.begin():
                    # Fetch donor and recipient com uma única operação para evitar condições de corrida
                    donor_result = await session.execute(select(User).where(User.id == user_id))
                    donor = donor_result.scalar_one_or_none()
                    recipient_result = await session.execute(select(User).where(User.nickname == nickname))
                    recipient = recipient_result.scalar_one_or_none()

                    # Validações completas antes de qualquer modificação
                    if not donor or not recipient:
                        await callback.answer("Usuário não encontrado.", show_alert=True)
                        return

                    if donor.coins < donation_quantity:
                        await callback.answer("Você não tem pokecoins suficientes.", show_alert=True)
                        return

                    # Transferência atômica das pokecoins
                    donor.coins -= donation_quantity
                    recipient.coins += donation_quantity

            # Remover a transação pendente após o sucesso
            if user_id in active_coin_donations:
                del active_coin_donations[user_id]

            # Feedback para o usuário após operação bem-sucedida
            await callback.message.edit_text(
                f"✅ Doação concluída! Você doou {donation_quantity} pokecoins para {nickname}.",
                parse_mode=ParseMode.MARKDOWN
            )
            await callback.answer("Doação realizada com sucesso!", show_alert=True)
            
        except Exception as e:
            logger.error(f"Erro ao processar doação: {str(e)}")
            
            # Remover a transação pendente em caso de erro
            if user_id in active_coin_donations:
                del active_coin_donations[user_id]
                
            # Tratamento de erro durante a transferência
            await callback.message.edit_text(
                "❌ **Erro:** Ocorreu um problema durante a doação. Tente novamente mais tarde.",
                parse_mode=ParseMode.MARKDOWN
            )
            await callback.answer("Erro durante a doação.", show_alert=True)
    except Exception as e:
        logger.error(f"Erro global em confirm_coin_donation: {str(e)}", exc_info=True)
        
        # Remover a transação pendente em caso de erro global
        if user_id in active_coin_donations:
            del active_coin_donations[user_id]
            
        await callback.answer("Erro ao processar a doação.", show_alert=True)

@router.callback_query(lambda call: call.data == "cancel_coin_donation")
async def cancel_coin_donation(callback: types.CallbackQuery):
    """
    Cancels any pending donation action.
    """
    user_id = callback.from_user.id
    
    # Remover a transação pendente
    if user_id in active_coin_donations:
        del active_coin_donations[user_id]
        
    await callback.message.edit_text("❌ Doação cancelada.", parse_mode=ParseMode.MARKDOWN)
    await callback.answer("Doação cancelada.", show_alert=True)

def cleanup_pending_transactions():
    """Remove transações pendentes antigas do dicionário"""
    current_time = time.time()
    cleaned = 0
    for uid in list(active_coin_donations.keys()):
        if current_time - active_coin_donations[uid] > TRANSACTION_TIMEOUT:
            del active_coin_donations[uid]
            cleaned += 1
    
    if cleaned > 0:
        logger.info(f"Limpeza de doações de moedas: {cleaned} transações expiradas removidas")