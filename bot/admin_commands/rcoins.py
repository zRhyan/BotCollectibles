import os
import logging
import time
from dotenv import load_dotenv
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from sqlalchemy.future import select
from sqlalchemy import update
from database.models import User
from database.session import get_session

# Configurar logging
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

ALLOWED_USERNAMES = os.getenv("ALLOWED_USERNAMES", "").split(",")  # Comma-separated list of allowed Telegram usernames

router = Router()

# Dicionário para rastrear transações pendentes
# Formato: {user_id: timestamp}
pending_coin_transactions = {}

# Tempo máximo (em segundos) que uma transação pode ficar pendente
TRANSACTION_TIMEOUT = 10  # 10 segundos

@router.message(Command("rcoins"))
async def distribute_coins_command(message: types.Message):
    """
    Admin command to distribute coins.
    Usage:
    - /rcoins quantidade (distributes to all users)
    - /rcoins nickname quantidade (distributes to a specific user)
    """
    user_id = message.from_user.id
    current_time = time.time()
    
    # Verificar se o usuário já possui uma transação pendente
    if user_id in pending_coin_transactions:
        await message.reply(
            "⚠️ **Já existe um processo em andamento!**\n"
            "Por favor, aguarde alguns instantes antes de tentar novamente.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Registrar a transação pendente
    pending_coin_transactions[user_id] = current_time
    
    try:
        # Check if the user is allowed
        if message.from_user.username not in ALLOWED_USERNAMES:
            await message.reply(
                "🚫 **Acesso negado!** Você não tem permissão para usar este comando.",
                parse_mode=ParseMode.MARKDOWN
            )
            if user_id in pending_coin_transactions:
                del pending_coin_transactions[user_id]
            return

        # Check if the user is an admin in a separate session
        is_admin = False
        try:
            async with get_session() as session:
                result = await session.execute(select(User).where(User.id == user_id))
                admin_user = result.scalar_one_or_none()
                is_admin = admin_user is not None and admin_user.is_admin == 1
        except Exception as e:
            logger.error(f"Erro ao verificar permissões admin: {str(e)}")
            if user_id in pending_coin_transactions:
                del pending_coin_transactions[user_id]
            await message.reply(
                "❌ **Erro ao verificar permissões.** Por favor, tente novamente mais tarde.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        if not is_admin:
            await message.reply(
                "🚫 **Acesso negado!** Somente administradores podem usar este comando.",
                parse_mode=ParseMode.MARKDOWN
            )
            if user_id in pending_coin_transactions:
                del pending_coin_transactions[user_id]
            return

        # Parse the command arguments
        text_parts = message.text.split(maxsplit=2)
        if len(text_parts) < 2:
            await message.reply(
                "❗ **Erro:** Você precisa fornecer a quantidade ou o nickname e a quantidade.\n"
                "Exemplo:\n"
                "`/rcoins 100` (para todos os usuários)\n"
                "`/rcoins nickname 100` (para um usuário específico)",
                parse_mode=ParseMode.MARKDOWN
            )
            if user_id in pending_coin_transactions:
                del pending_coin_transactions[user_id]
            return

        # Handle the case for all users
        if len(text_parts) == 2:
            try:
                quantity = int(text_parts[1])
            except ValueError:
                await message.reply(
                    "❗ **Erro:** A quantidade deve ser um número inteiro válido.",
                    parse_mode=ParseMode.MARKDOWN
                )
                if user_id in pending_coin_transactions:
                    del pending_coin_transactions[user_id]
                return

            try:
                # Update coins for all users in a well-defined transaction
                async with get_session() as session:
                    async with session.begin():
                        result = await session.execute(
                            update(User).values(coins=User.coins + quantity)
                        )
                        rows_affected = result.rowcount
                
                # Limpar transação após sucesso
                if user_id in pending_coin_transactions:
                    del pending_coin_transactions[user_id]

                await message.reply(
                    f"✅ **Sucesso!** {quantity} pokecoins foram distribuídas para {rows_affected} usuários.",
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                logger.error(f"Erro ao distribuir coins: {str(e)}")
                if user_id in pending_coin_transactions:
                    del pending_coin_transactions[user_id]
                await message.reply(
                    f"❌ **Erro:** Ocorreu um problema ao distribuir as pokecoins.\n"
                    f"Detalhes: `{str(e)[:100]}...`",
                    parse_mode=ParseMode.MARKDOWN
                )
            return

        # Handle the case for a specific user
        if len(text_parts) == 3:
            nickname = text_parts[1].strip()
            try:
                quantity = int(text_parts[2])
            except ValueError:
                await message.reply(
                    "❗ **Erro:** A quantidade deve ser um número inteiro válido.",
                    parse_mode=ParseMode.MARKDOWN
                )
                if user_id in pending_coin_transactions:
                    del pending_coin_transactions[user_id]
                return

            try:
                # Update coins for the specific user in a well-defined transaction
                async with get_session() as session:
                    async with session.begin():
                        result = await session.execute(select(User).where(User.nickname == nickname))
                        user = result.scalar_one_or_none()

                        if not user:
                            await message.reply(
                                f"❌ **Erro:** Nenhum usuário encontrado com o nickname `{nickname}`.",
                                parse_mode=ParseMode.MARKDOWN
                            )
                            if user_id in pending_coin_transactions:
                                del pending_coin_transactions[user_id]
                            return

                        coins_before = user.coins
                        user.coins += quantity

                # Limpar transação após sucesso
                if user_id in pending_coin_transactions:
                    del pending_coin_transactions[user_id]

                await message.reply(
                    f"✅ **Sucesso!** {quantity} pokecoins foram adicionadas ao usuário `{nickname}`.\n"
                    f"Total anterior: {coins_before}, Novo total: {user.coins}",
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                logger.error(f"Erro ao adicionar coins para {nickname}: {str(e)}")
                if user_id in pending_coin_transactions:
                    del pending_coin_transactions[user_id]
                await message.reply(
                    f"❌ **Erro:** Ocorreu um problema ao adicionar pokecoins para `{nickname}`.\n"
                    f"Detalhes: `{str(e)[:100]}...`",
                    parse_mode=ParseMode.MARKDOWN
                )
    except Exception as global_err:
        logger.error(f"Global error in rcoins: {str(global_err)}", exc_info=True)
        # Limpar transação pendente em caso de erro global
        if user_id in pending_coin_transactions:
            del pending_coin_transactions[user_id]
        await message.reply(
            "❌ **Erro crítico:** Ocorreu um problema inesperado.",
            parse_mode=ParseMode.MARKDOWN
        )

# Função para limpeza periódica
def cleanup_pending_transactions():
    """Remove transações pendentes antigas do dicionário"""
    current_time = time.time()
    cleaned = 0
    for uid in list(pending_coin_transactions.keys()):
        if current_time - pending_coin_transactions[uid] > TRANSACTION_TIMEOUT:
            del pending_coin_transactions[uid]
            cleaned += 1
    
    if cleaned > 0:
        logger.info(f"Limpeza de transações rcoins: {cleaned} transações expiradas removidas")