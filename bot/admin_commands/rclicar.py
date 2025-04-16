import os
import logging
from dotenv import load_dotenv
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from sqlalchemy.future import select
from sqlalchemy import update, func
from database.models import User
from database.session import get_session

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

ALLOWED_USERNAMES = os.getenv("ALLOWED_USERNAMES", "").split(",")  # Comma-separated list of allowed Telegram usernames

router = Router()

@router.message(Command("rclicar"))
async def reset_pokeballs_command(message: types.Message):
    """
    Admin command to distribute Pokébolas.
    Usage:
    - /rclicar quantidade (distributes to all users)
    - /rclicar nickname quantidade (distributes to a specific user)
    """
    # Check if the user is allowed
    if message.from_user.username not in ALLOWED_USERNAMES:
        await message.reply(
            "🚫 **Acesso negado!** Você não tem permissão para usar este comando.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Check if the user is an admin
    async with get_session() as session:
        result = await session.execute(select(User).where(User.id == message.from_user.id))
        admin_user = result.scalar_one_or_none()

        if not admin_user or admin_user.is_admin == 0:
            await message.reply(
                "🚫 **Acesso negado!** Somente administradores podem usar este comando.",
                parse_mode=ParseMode.MARKDOWN
            )
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
            return

        # Update Pokébolas for all users with better error handling and verification
        try:
            async with get_session() as session:
                # Primeiro contar quantos usuários existem para verificação posterior
                count_result = await session.execute(select(func.count(User.id)))
                total_users = count_result.scalar_one()
                
                if total_users == 0:
                    await message.reply(
                        "⚠️ **Aviso:** Não há usuários registrados no sistema.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    return
                
                # Iniciar uma transação explícita
                async with session.begin():
                    # Atualizar pokebolas para todos os usuários
                    result = await session.execute(
                        update(User)
                        .values(pokeballs=User.pokeballs + quantity)
                        .execution_options(synchronize_session=False)
                    )
                    
                    # Verificar quantas linhas foram afetadas
                    rows_affected = result.rowcount
                    
                    if rows_affected != total_users:
                        logger.warning(
                            f"Discrepância na atualização: {rows_affected} usuários atualizados de um total de {total_users}"
                        )
                
                # Log da operação
                admin_username = message.from_user.username or str(message.from_user.id)
                logger.info(f"Admin {admin_username} adicionou {quantity} pokebolas para {rows_affected} usuários")
                
                await message.reply(
                    f"✅ **Sucesso!** {quantity} Pokébolas foram distribuídas para {rows_affected} usuários.\n"
                    f"Total de usuários no sistema: {total_users}",
                    parse_mode=ParseMode.MARKDOWN
                )
        
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Erro ao distribuir pokebolas: {error_msg}")
            await message.reply(
                f"❌ **Erro:** Ocorreu um problema ao distribuir as Pokébolas.\n"
                f"Detalhes: `{error_msg[:100]}...`",
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
            return

        # Update Pokébolas for the specific user with better error handling
        try:
            async with get_session() as session:
                result = await session.execute(select(User).where(User.nickname == nickname))
                user = result.scalar_one_or_none()

                if not user:
                    await message.reply(
                        f"❌ **Erro:** Nenhum usuário encontrado com o nickname `{nickname}`.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    return
                
                # Valor atual para confirmação
                pokeballs_before = user.pokeballs or 0
                
                # Atualizar e confirmar
                if user.pokeballs is None:
                    user.pokeballs = quantity
                else:
                    user.pokeballs += quantity
                await session.commit()
                
                # Log da operação
                admin_username = message.from_user.username or str(message.from_user.id)
                logger.info(
                    f"Admin {admin_username} adicionou {quantity} pokebolas para o usuário {nickname}. "
                    f"Total anterior: {pokeballs_before}, Novo total: {user.pokeballs}"
                )
                
                await message.reply(
                    f"✅ **Sucesso!** {quantity} Pokébolas foram adicionadas ao usuário `{nickname}`.\n"
                    f"Total anterior: {pokeballs_before}, Novo total: {user.pokeballs}",
                    parse_mode=ParseMode.MARKDOWN
                )
        
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Erro ao adicionar pokebolas para {nickname}: {error_msg}")
            await message.reply(
                f"❌ **Erro:** Ocorreu um problema ao adicionar Pokébolas para `{nickname}`.\n"
                f"Detalhes: `{error_msg[:100]}...`",
                parse_mode=ParseMode.MARKDOWN
            )