from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from sqlalchemy import text
from database.session import get_session
from database.models import User, Card, Group, Category, Tag

router = Router()

@router.message(Command(commands=["checkduplicates", "checkdup"]))
async def check_duplicates(message: types.Message):
    """
    Verifica registros duplicados no banco de dados.
    Comando administrativo para encontrar e reportar inconsistências.
    """
    # Verificar se o usuário é um administrador
    async with get_session() as session:
        result = await session.execute(
            text("SELECT id FROM users WHERE id = :user_id AND is_admin = 1"),
            {"user_id": message.from_user.id}
        )
        is_admin = result.first() is not None

    if not is_admin:
        await message.reply(
            "🚫 **Acesso negado!** Somente administradores podem usar este comando.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    await message.reply("🔍 Verificando duplicações no banco de dados. Por favor, aguarde...")
    
    duplicates = []
    
    async with get_session() as session:
        # Verificar grupos duplicados (mesmo nome e categoria)
        result = await session.execute(
            text("""
                SELECT g.name, c.name as category, COUNT(*) as count
                FROM groups g
                JOIN categories c ON g.category_id = c.id
                GROUP BY g.name, c.name
                HAVING COUNT(*) > 1
                ORDER BY count DESC
            """)
        )
        group_duplicates = result.fetchall()
        if group_duplicates:
            duplicates.append("**Grupos duplicados:**")
            for row in group_duplicates:
                duplicates.append(f"- Nome: `{row[0]}`, Categoria: `{row[1]}`, Quantidade: `{row[2]}`")
        
        # Verificar cards duplicados (mesmo nome)
        result = await session.execute(
            text("""
                SELECT name, COUNT(*) as count
                FROM cards
                GROUP BY name
                HAVING COUNT(*) > 1
                ORDER BY count DESC
            """)
        )
        card_duplicates = result.fetchall()
        if card_duplicates:
            duplicates.append("\n**Cards duplicados:**")
            for row in card_duplicates:
                duplicates.append(f"- Nome: `{row[0]}`, Quantidade: `{row[1]}`")
        
        # Verificar categorias duplicadas (mesmo nome)
        result = await session.execute(
            text("""
                SELECT name, COUNT(*) as count
                FROM categories
                GROUP BY name
                HAVING COUNT(*) > 1
                ORDER BY count DESC
            """)
        )
        category_duplicates = result.fetchall()
        if category_duplicates:
            duplicates.append("\n**Categorias duplicadas:**")
            for row in category_duplicates:
                duplicates.append(f"- Nome: `{row[0]}`, Quantidade: `{row[1]}`")
        
        # Verificar tags duplicadas (mesmo nome)
        result = await session.execute(
            text("""
                SELECT name, COUNT(*) as count
                FROM tags
                GROUP BY name
                HAVING COUNT(*) > 1
                ORDER BY count DESC
            """)
        )
        tag_duplicates = result.fetchall()
        if tag_duplicates:
            duplicates.append("\n**Tags duplicadas:**")
            for row in tag_duplicates:
                duplicates.append(f"- Nome: `{row[0]}`, Quantidade: `{row[1]}`")
    
    if duplicates:
        await message.reply(
            "⚠️ **Registros duplicados encontrados:**\n\n" + "\n".join(duplicates),
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await message.reply(
            "✅ **Nenhuma duplicação encontrada!** O banco de dados parece estar consistente.",
            parse_mode=ParseMode.MARKDOWN
        )
