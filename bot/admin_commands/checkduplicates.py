from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from sqlalchemy import text, select, func
from database.session import get_session
from database.models import User, Card, Group, Category, Tag
import logging
import traceback

# Configurar logger
logger = logging.getLogger(__name__)

router = Router()

@router.message(Command(commands=["checkduplicates", "checkdup"]))
async def check_duplicates(message: types.Message):
    """
    Verifica registros duplicados no banco de dados.
    Comando administrativo para encontrar e reportar inconsistências.
    """
    logger.info(f"Comando /checkduplicates iniciado pelo usuário {message.from_user.id} ({message.from_user.username})")
    
    # Verificar se o usuário é um administrador usando o modelo User diretamente
    try:
        async with get_session() as session:
            admin_result = await session.execute(
                select(User).where(User.id == message.from_user.id, User.is_admin == 1)
            )
            admin_user = admin_result.scalars().first()
            
            if not admin_user:
                logger.warning(f"Tentativa de acesso não autorizado ao comando admin por {message.from_user.id}")
                await message.reply(
                    "🚫 **Acesso negado!** Somente administradores podem usar este comando.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            
            logger.info(f"Acesso autorizado para {message.from_user.id}")
            status_msg = await message.reply("🔍 **Verificando duplicações no banco de dados...**\nPor favor, aguarde...", parse_mode=ParseMode.MARKDOWN)
            
            try:
                # Lista para armazenar mensagens sobre duplicações
                duplicates = []
                
                # 1. Verificar grupos duplicados (mesmo nome e categoria)
                logger.info("Verificando grupos duplicados")
                groups_query = """
                    SELECT g.id, g.name as name, c.name as category_name, COUNT(*) OVER (PARTITION BY g.name, c.name) as count
                    FROM groups g
                    JOIN categories c ON g.category_id = c.id
                    ORDER BY count DESC, name
                """
                group_result = await session.execute(text(groups_query))
                group_rows = group_result.all()
                
                # Processar resultados para identificar duplicados
                group_duplicates = {}
                for row in group_rows:
                    if row.count > 1:
                        key = f"{row.name}_{row.category_name}"
                        if key not in group_duplicates:
                            group_duplicates[key] = []
                        group_duplicates[key].append(row)
                
                if group_duplicates:
                    duplicates.append("**Grupos duplicados:**")
                    for key, rows in group_duplicates.items():
                        name = rows[0].name
                        category = rows[0].category_name
                        count = rows[0].count
                        ids = ", ".join(str(row.id) for row in rows)
                        duplicates.append(f"- Nome: `{name}`, Categoria: `{category}`, Quantidade: `{count}`, IDs: `{ids}`")
                
                # 2. Verificar cards duplicados (mesmo nome)
                logger.info("Verificando cards duplicados")
                cards_query = """
                    SELECT id, name, COUNT(*) OVER (PARTITION BY name) as count 
                    FROM cards 
                    ORDER BY count DESC, name
                """
                card_result = await session.execute(text(cards_query))
                card_rows = card_result.all()
                
                # Processar resultados
                card_duplicates = {}
                for row in card_rows:
                    if row.count > 1:
                        if row.name not in card_duplicates:
                            card_duplicates[row.name] = []
                        card_duplicates[row.name].append(row)
                
                if card_duplicates:
                    duplicates.append("\n**Cards duplicados:**")
                    for name, rows in card_duplicates.items():
                        count = rows[0].count
                        ids = ", ".join(str(row.id) for row in rows)
                        duplicates.append(f"- Nome: `{name}`, Quantidade: `{count}`, IDs: `{ids}`")
                
                # 3. Verificar categorias duplicadas (mesmo nome)
                logger.info("Verificando categorias duplicadas")
                categories_query = """
                    SELECT id, name, COUNT(*) OVER (PARTITION BY name) as count 
                    FROM categories 
                    ORDER BY count DESC, name
                """
                category_result = await session.execute(text(categories_query))
                category_rows = category_result.all()
                
                # Processar resultados
                category_duplicates = {}
                for row in category_rows:
                    if row.count > 1:
                        if row.name not in category_duplicates:
                            category_duplicates[row.name] = []
                        category_duplicates[row.name].append(row)
                
                if category_duplicates:
                    duplicates.append("\n**Categorias duplicadas:**")
                    for name, rows in category_duplicates.items():
                        count = rows[0].count
                        ids = ", ".join(str(row.id) for row in rows)
                        duplicates.append(f"- Nome: `{name}`, Quantidade: `{count}`, IDs: `{ids}`")
                
                # 4. Verificar tags duplicadas (mesmo nome)
                logger.info("Verificando tags duplicadas")
                tags_query = """
                    SELECT id, name, COUNT(*) OVER (PARTITION BY name) as count 
                    FROM tags 
                    ORDER BY count DESC, name
                """
                tag_result = await session.execute(text(tags_query))
                tag_rows = tag_result.all()
                
                # Processar resultados
                tag_duplicates = {}
                for row in tag_rows:
                    if row.count > 1:
                        if row.name not in tag_duplicates:
                            tag_duplicates[row.name] = []
                        tag_duplicates[row.name].append(row)
                
                if tag_duplicates:
                    duplicates.append("\n**Tags duplicadas:**")
                    for name, rows in tag_duplicates.items():
                        count = rows[0].count
                        ids = ", ".join(str(row.id) for row in rows)
                        duplicates.append(f"- Nome: `{name}`, Quantidade: `{count}`, IDs: `{ids}`")
                
                # 5. Verificar duplicados no inventário (mesmo usuário e card)
                logger.info("Verificando duplicações no inventário")
                inventory_query = """
                    SELECT user_id, card_id, COUNT(*) as count
                    FROM inventory
                    GROUP BY user_id, card_id
                    HAVING COUNT(*) > 1
                    ORDER BY count DESC
                """
                inventory_result = await session.execute(text(inventory_query))
                inventory_duplicates = inventory_result.all()
                
                if inventory_duplicates:
                    duplicates.append("\n**Inventário com duplicações:**")
                    for row in inventory_duplicates:
                        duplicates.append(f"- Usuário ID: `{row.user_id}`, Card ID: `{row.card_id}`, Entradas: `{row.count}`")
                
                # Enviar resultados
                if duplicates:
                    logger.info(f"Encontradas {len(duplicates)} entradas com duplicações")
                    # Dividir a mensagem se for muito grande (limite do Telegram é ~4096 caracteres)
                    full_message = "⚠️ **Registros duplicados encontrados:**\n\n" + "\n".join(duplicates)
                    
                    # Enviar em partes se necessário
                    if len(full_message) > 4000:
                        chunks = [full_message[i:i+4000] for i in range(0, len(full_message), 4000)]
                        await status_msg.edit_text(chunks[0], parse_mode=ParseMode.MARKDOWN)
                        
                        for chunk in chunks[1:]:
                            await message.answer(chunk, parse_mode=ParseMode.MARKDOWN)
                    else:
                        await status_msg.edit_text(full_message, parse_mode=ParseMode.MARKDOWN)
                else:
                    logger.info("Nenhuma duplicação encontrada no banco de dados")
                    await status_msg.edit_text(
                        "✅ **Verificação concluída!** Nenhuma duplicação encontrada no banco de dados.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    
            except Exception as e:
                error_msg = str(e)
                stack_trace = traceback.format_exc()
                logger.error(f"Erro ao verificar duplicações: {error_msg}\n{stack_trace}")
                
                await status_msg.edit_text(
                    f"❌ **Erro ao verificar duplicações:**\n`{error_msg[:1000]}`\n\n"
                    "Verifique os logs do sistema para mais detalhes.",
                    parse_mode=ParseMode.MARKDOWN
                )
    except Exception as e:
        logger.error(f"Erro ao executar comando /checkduplicates: {str(e)}\n{traceback.format_exc()}")
        await message.reply("❌ Ocorreu um erro inesperado ao executar o comando.", parse_mode=ParseMode.MARKDOWN)

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
