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
            # Verificar categorias duplicadas - com IDs e nomes completos
            result = await session.execute(text(
                """
                SELECT c1.id, c1.name, c2.id AS duplicate_id, c2.name AS duplicate_name
                FROM categories c1
                JOIN categories c2 ON LOWER(c1.name) = LOWER(c2.name) AND c1.id < c2.id
                ORDER BY LOWER(c1.name)
                """
            ))
            category_dups = result.fetchall()
            
            if category_dups:
                duplicates.append("**Categorias duplicadas:**")
                # Agrupar duplicatas pelo nome para melhor visualização
                categories_by_name = {}
                for row in category_dups:
                    name = row[1].lower()
                    if name not in categories_by_name:
                        categories_by_name[name] = []
                    # Adicionar o original se for o primeiro
                    if not categories_by_name[name]:
                        categories_by_name[name].append((row[0], row[1]))
                    # Adicionar o duplicado
                    categories_by_name[name].append((row[2], row[3]))
                
                # Mostrar cada grupo de duplicatas
                for name, entries in categories_by_name.items():
                    duplicates.append(f"\n• Categoria: `{name}`")
                    for idx, (id, full_name) in enumerate(entries):
                        duplicates.append(f"  {idx+1}. ID: `{id}`, Nome completo: `{full_name}`")
            
            logger.debug("Verificando grupos duplicados")
            # Verificar grupos duplicados - com IDs, nomes e categorias
            result = await session.execute(text(
                """
                SELECT g1.id, g1.name, c1.name as category_name, 
                       g2.id AS duplicate_id, g2.name AS duplicate_name, c2.name as duplicate_category
                FROM groups g1
                JOIN categories c1 ON g1.category_id = c1.id
                JOIN groups g2 ON LOWER(g1.name) = LOWER(g2.name) AND g1.id < g2.id
                JOIN categories c2 ON g2.category_id = c2.id
                ORDER BY LOWER(g1.name)
                """
            ))
            group_dups = result.fetchall()
            
            if group_dups:
                duplicates.append("\n**Grupos com nomes duplicados:**")
                # Agrupar duplicatas pelo nome para melhor visualização
                groups_by_name = {}
                for row in group_dups:
                    name = row[1].lower()
                    if name not in groups_by_name:
                        groups_by_name[name] = []
                    # Adicionar o original se for o primeiro
                    if not groups_by_name[name]:
                        groups_by_name[name].append((row[0], row[1], row[2]))
                    # Adicionar o duplicado
                    groups_by_name[name].append((row[3], row[4], row[5]))
                
                # Mostrar cada grupo de duplicatas
                for name, entries in groups_by_name.items():
                    duplicates.append(f"\n• Grupo: `{name}`")
                    for idx, (id, full_name, category) in enumerate(entries):
                        duplicates.append(f"  {idx+1}. ID: `{id}`, Nome completo: `{full_name}`, Categoria: `{category}`")
            
            logger.debug("Verificando cards duplicados")
            # Verificar cards duplicados - com IDs, nomes e raridades
            result = await session.execute(text(
                """
                SELECT c1.id, c1.name, c1.rarity, g1.name as group_name,
                       c2.id AS duplicate_id, c2.name AS duplicate_name, c2.rarity as duplicate_rarity, g2.name as duplicate_group
                FROM cards c1
                JOIN groups g1 ON c1.group_id = g1.id
                JOIN cards c2 ON LOWER(c1.name) = LOWER(c2.name) AND c1.id < c2.id
                JOIN groups g2 ON c2.group_id = g2.id
                ORDER BY LOWER(c1.name)
                """
            ))
            card_dups = result.fetchall()
            
            if card_dups:
                duplicates.append("\n**Cards com nomes duplicados:**")
                # Agrupar duplicatas pelo nome para melhor visualização
                cards_by_name = {}
                for row in card_dups:
                    name = row[1].lower()
                    if name not in cards_by_name:
                        cards_by_name[name] = []
                    # Adicionar o original se for o primeiro
                    if not cards_by_name[name]:
                        cards_by_name[name].append((row[0], row[1], row[2], row[3]))
                    # Adicionar o duplicado
                    cards_by_name[name].append((row[4], row[5], row[6], row[7]))
                
                # Mostrar cada grupo de duplicatas
                for name, entries in cards_by_name.items():
                    duplicates.append(f"\n• Card: `{name}`")
                    for idx, (id, full_name, rarity, group) in enumerate(entries):
                        duplicates.append(f"  {idx+1}. ID: `{id}`, Nome completo: `{full_name}`, Raridade: `{rarity}`, Grupo: `{group}`")

        if duplicates:
            logger.debug(f"Encontradas {len(duplicates)} linhas de duplicação")
            response_text = "⚠️ **Registros duplicados encontrados:**\n\n" + "\n".join(duplicates)
            
            # Dividir mensagem se for muito longa
            if len(response_text) > 4000:
                parts = []
                current_part = "⚠️ **Registros duplicados encontrados:**\n\n"
                
                for line in duplicates:
                    if len(current_part + line + "\n") > 4000:
                        parts.append(current_part)
                        current_part = "⚠️ **Continuação:**\n\n" + line + "\n"
                    else:
                        current_part += line + "\n"
                
                if current_part:
                    parts.append(current_part)
                
                # Enviar primeira parte editando a mensagem original
                await status_msg.edit_text(parts[0], parse_mode=ParseMode.MARKDOWN)
                
                # Enviar partes restantes como novas mensagens
                for part in parts[1:]:
                    await message.answer(part, parse_mode=ParseMode.MARKDOWN)
            else:
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
