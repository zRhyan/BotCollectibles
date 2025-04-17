from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from sqlalchemy import text, select, func
from database.session import get_session
from database.models import User, Card, Group, Category, Tag
import logging
import sys

# Configurar logger com saída para stdout para depuração imediata
logger = logging.getLogger(__name__)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

router = Router()

@router.message(Command(commands=["checkduplicates", "checkdup"]))
async def check_duplicates(message: types.Message):
    """Verifica registros duplicados no banco de dados."""
    logger.debug(f"Comando /checkduplicates iniciado por {message.from_user.id}")

    try:
        # Verificar se o usuário é admin
        async with get_session() as session:
            logger.debug("Verificando se usuário é admin")
            result = await session.execute(
                select(User).where(User.id == message.from_user.id)
            )
            user = result.scalars().first()
            
            if not user or user.is_admin == 0:
                logger.debug(f"Usuário {message.from_user.id} não é admin")
                await message.reply("🚫 Acesso negado! Somente administradores podem usar este comando.")
                return

        logger.debug("Usuário é admin, prosseguindo")
        status_msg = await message.reply("🔍 Verificando duplicações... Por favor, aguarde.")

        duplicates = []
        
        async with get_session() as session:
            logger.debug("Verificando categorias duplicadas")
            # Verificar categorias duplicadas - abordagem simples
            result = await session.execute(text(
                "SELECT name, COUNT(*) as count FROM categories GROUP BY name HAVING COUNT(*) > 1"
            ))
            category_dups = result.fetchall()
            if category_dups:
                duplicates.append("**Categorias duplicadas:**")
                for row in category_dups:
                    duplicates.append(f"- Nome: `{row[0]}`, Quantidade: `{row[1]}`")
            
            logger.debug("Verificando grupos duplicados")
            # Verificar grupos duplicados - abordagem simples
            result = await session.execute(text(
                "SELECT g.name, COUNT(*) as count FROM groups g GROUP BY g.name HAVING COUNT(*) > 1"
            ))
            group_dups = result.fetchall()
            if group_dups:
                duplicates.append("\n**Grupos com mesmo nome:**")
                for row in group_dups:
                    duplicates.append(f"- Nome: `{row[0]}`, Quantidade: `{row[1]}`")
            
            logger.debug("Verificando cards duplicados")
            # Verificar cards duplicados - abordagem simples
            result = await session.execute(text(
                "SELECT name, COUNT(*) as count FROM cards GROUP BY name HAVING COUNT(*) > 1"
            ))
            card_dups = result.fetchall()
            if card_dups:
                duplicates.append("\n**Cards duplicados:**")
                for row in card_dups:
                    duplicates.append(f"- Nome: `{row[0]}`, Quantidade: `{row[1]}`")

        if duplicates:
            logger.debug(f"Encontradas {len(duplicates)} linhas de duplicação")
            response_text = "⚠️ **Registros duplicados encontrados:**\n\n" + "\n".join(duplicates)
            await status_msg.edit_text(response_text, parse_mode=ParseMode.MARKDOWN)
        else:
            logger.debug("Nenhuma duplicação encontrada")
            await status_msg.edit_text("✅ Nenhuma duplicação encontrada!", parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        logger.error(f"Erro no comando /checkduplicates: {str(e)}", exc_info=True)
        await message.reply(f"❌ Erro ao verificar duplicações: `{str(e)[:200]}`", parse_mode=ParseMode.MARKDOWN)

# Comando adicional para corrigir duplicações (apenas para admins avançados)
@router.message(Command(commands=["fixduplicates"]))
async def fix_duplicates(message: types.Message):
    """
    Tenta corrigir automaticamente algumas duplicações comuns no banco de dados.
    Apenas para administradores com experiência técnica.
    """
    logger.info(f"Comando /fixduplicates iniciado pelo usuário {message.from_user.id}")
    
    try:
        async with get_session() as session:
            # Verificar se o usuário é um administrador
            admin_result = await session.execute(
                select(User).where(User.id == message.from_user.id, User.is_admin == 1)
            )
            admin_user = admin_result.scalars().first()
            
            if not admin_user:
                return
            
            status_msg = await message.reply("⚙️ **Iniciando correção de duplicações...**\nIsso pode levar algum tempo.", parse_mode=ParseMode.MARKDOWN)
            fix_report = []
            
            # Aqui implementaríamos a lógica de correção
            # Por segurança, este é apenas um esboço - não implementa correções reais
            
            await status_msg.edit_text(
                "⚠️ **Atenção:** A correção automática de duplicações não está implementada por segurança.\n\n"
                "Por favor, entre em contato com o desenvolvedor para resolver manualmente as duplicações identificadas.",
                parse_mode=ParseMode.MARKDOWN
            )
    except Exception as e:
        logger.error(f"Erro ao executar /fixduplicates: {str(e)}")
        await message.reply("❌ Ocorreu um erro ao tentar corrigir duplicações.", parse_mode=ParseMode.MARKDOWN)
