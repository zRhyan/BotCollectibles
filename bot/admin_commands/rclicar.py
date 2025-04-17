import os
import logging
import time
from dotenv import load_dotenv
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from sqlalchemy.future import select
from sqlalchemy import update, func
from database.models import User
from database.session import get_session, run_transaction

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

ALLOWED_USERNAMES = os.getenv("ALLOWED_USERNAMES", "").split(",")  # Comma-separated list of allowed Telegram usernames

router = Router()

# Dicionário para rastrear transações pendentes
# Formato: {user_id: timestamp}
pending_transactions = {}

# Tempo máximo (em segundos) que uma transação pode ficar pendente
TRANSACTION_TIMEOUT = 10  # 10 segundos

@router.message(Command("rclicar"))
async def reset_pokeballs_command(message: types.Message):
    """
    Admin command to distribute Pokébolas.
    Usage:
    - /rclicar quantidade (distributes to all users)
    - /rclicar nickname quantidade (distributes to a specific user)
    """
    user_id = message.from_user.id
    current_time = time.time()
    
    # Verificar se o usuário já possui uma transação pendente
    if user_id in pending_transactions:
        await message.reply(
            "⚠️ **Já existe um processo em andamento!**\n"
            "Por favor, aguarde alguns instantes antes de tentar novamente.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Registrar a transação pendente
    pending_transactions[user_id] = current_time
    
    try:
        # Check if the user is allowed
        if message.from_user.username not in ALLOWED_USERNAMES:
            await message.reply(
                "🚫 **Acesso negado!** Você não tem permissão para usar este comando.",
                parse_mode=ParseMode.MARKDOWN
            )
            if user_id in pending_transactions:
                del pending_transactions[user_id]
            return

        # Check if the user is an admin using safe transaction
        async def verify_admin(session):
            result = await session.execute(select(User).where(User.id == user_id))
            admin_user = result.scalar_one_or_none()
            return admin_user is not None and admin_user.is_admin == 1
            
        success, is_admin, error = await run_transaction(
            verify_admin, 
            "Erro ao verificar permissões admin"
        )
            
        if not success:
            if user_id in pending_transactions:
                del pending_transactions[user_id]
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
            if user_id in pending_transactions:
                del pending_transactions[user_id]
            return

        # Parse the command arguments
        text_parts = message.text.split(maxsplit=2)
        if len(text_parts) < 2:
            await message.reply(
                "❗ **Erro:** Você precisa fornecer a quantidade ou o nickname e a quantidade.\n"
                "Exemplo:\n"
                "`/rclicar 10` (para todos os usuários)\n"
                "`/rclicar nickname 10` (para um usuário específico)",
                parse_mode=ParseMode.MARKDOWN
            )
            if user_id in pending_transactions:
                del pending_transactions[user_id]
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
                if user_id in pending_transactions:
                    del pending_transactions[user_id]
                return

            # Definir operações para obter contagem e atualizar pokébolas
            async def update_all_users_pokeballs(session):
                # Contar usuários
                count_result = await session.execute(select(func.count(User.id)))
                total_users = count_result.scalar_one()
                
                if total_users == 0:
                    return {"total": 0, "updated": 0}
                
                # Atualizar pokebolas para todos os usuários
                result = await session.execute(
                    update(User)
                    .values(pokeballs=User.pokeballs + quantity)
                    .execution_options(synchronize_session=False)
                )
                
                # Retornar resultados
                return {
                    "total": total_users,
                    "updated": result.rowcount
                }
            
            # Executar operação em transação segura
            success, result, error = await run_transaction(
                update_all_users_pokeballs, 
                "Erro ao distribuir pokebolas"
            )
            
            # Limpar transação pendente
            if user_id in pending_transactions:
                del pending_transactions[user_id]
                
            if not success:
                await message.reply(
                    f"❌ **Erro:** Ocorreu um problema ao distribuir as Pokébolas.\n"
                    f"Detalhes: `{error[:100]}...`",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            
            # Log da operação
            admin_username = message.from_user.username or str(message.from_user.id)
            logger.info(f"Admin {admin_username} adicionou {quantity} pokebolas para {result['updated']} usuários")
            
            await message.reply(
                f"✅ **Sucesso!** {quantity} Pokébolas foram distribuídas para {result['updated']} usuários.\n"
                f"Total de usuários no sistema: {result['total']}",
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
                if user_id in pending_transactions:
                    del pending_transactions[user_id]
                return

            # Definir operação para atualizar pokébolas de usuário específico
            async def update_user_pokeballs(session):
                result = await session.execute(select(User).where(User.nickname == nickname))
                user = result.scalar_one_or_none()
                
                if not user:
                    return None
                
                # Valor atual para confirmação
                pokeballs_before = user.pokeballs or 0
                
                # Atualizar
                if user.pokeballs is None:
                    user.pokeballs = quantity
                else:
                    user.pokeballs += quantity
                
                return {
                    "before": pokeballs_before,
                    "after": user.pokeballs,
                    "nickname": user.nickname
                }
            
            # Executar operação em transação segura
            success, result, error = await run_transaction(
                update_user_pokeballs, 
                f"Erro ao adicionar pokebolas para {nickname}"
            )
            
            # Limpar transação pendente
            if user_id in pending_transactions:
                del pending_transactions[user_id]
            
            if not success:
                await message.reply(
                    f"❌ **Erro:** Ocorreu um problema ao adicionar Pokébolas.\n"
                    f"Detalhes: `{error[:100]}...`",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
                
            if result is None:
                await message.reply(
                    f"❌ **Erro:** Nenhum usuário encontrado com o nickname `{nickname}`.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            
            # Log da operação
            admin_username = message.from_user.username or str(message.from_user.id)
            logger.info(
                f"Admin {admin_username} adicionou {quantity} pokebolas para o usuário {nickname}. "
                f"Total anterior: {result['before']}, Novo total: {result['after']}"
            )
            
            await message.reply(
                f"✅ **Sucesso!** {quantity} Pokébolas foram adicionadas ao usuário `{nickname}`.\n"
                f"Total anterior: {result['before']}, Novo total: {result['after']}",
                parse_mode=ParseMode.MARKDOWN
            )

    except Exception as global_err:
        logger.error(f"Global error in rclicar: {str(global_err)}", exc_info=True)
        # Limpar transação pendente em caso de erro global
        if user_id in pending_transactions:
            del pending_transactions[user_id]
        await message.reply(
            "❌ **Erro crítico:** Ocorreu um problema inesperado.",
            parse_mode=ParseMode.MARKDOWN
        )

# Função para limpeza periódica
def cleanup_pending_transactions():
    """Remove transações pendentes antigas do dicionário"""
    current_time = time.time()
    cleaned = 0
    for uid in list(pending_transactions.keys()):
        if current_time - pending_transactions[uid] > TRANSACTION_TIMEOUT:
            del pending_transactions[uid]
            cleaned += 1
    
    if cleaned > 0:
        logger.info(f"Limpeza de transações rclicar: {cleaned} transações expiradas removidas")