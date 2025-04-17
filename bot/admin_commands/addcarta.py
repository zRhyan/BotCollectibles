from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError, InvalidRequestError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func
from database.models import User, Card, Group, Category, Tag, card_tags
from database.session import get_session
from bot.utils.image_utils import ensure_photo_file_id
import logging
import re
import asyncio
import time
import contextlib

# Configure logger
logger = logging.getLogger(__name__)

router = Router()

# Dicionário para rastrear transações pendentes de adição de cards
# Formato: {user_id: timestamp}
pending_card_additions = {}

# Tempo máximo (em segundos) que uma transação pode ficar pendente
TRANSACTION_TIMEOUT = 30  # 30 segundos

@router.message(Command(commands=["addcarta", "add"]))
async def add_card(message: types.Message):
    """
    Handles the /addcarta command to add a new card.
    Accepts images sent as photos or as Telegram files (documents).
    """
    user_id = message.from_user.id
    current_time = time.time()
    
    # Limpar transações antigas
    cleanup_pending_transactions()
    
    # Verificar se o usuário já possui uma transação pendente
    if user_id in pending_card_additions:
        await message.reply(
            "⚠️ **Já existe um processo de adição de card em andamento!**\n"
            "Por favor, conclua o processo atual ou aguarde alguns minutos para tentar novamente.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    try:
        # Registrar a transação pendente
        pending_card_additions[user_id] = current_time
        
        # Check if the user is an admin
        admin_verified = False
        try:
            # Usar uma sessão isolada apenas para verificar se é admin
            async with get_session() as admin_check_session:
                result = await admin_check_session.execute(select(User).where(User.id == user_id))
                user = result.scalars().first()
                admin_verified = user is not None and user.is_admin == 1
                
        except Exception as e:
            logger.error(f"Erro ao verificar permissões de admin: {str(e)}")
            # Limpar transação pendente em caso de erro
            if user_id in pending_card_additions:
                del pending_card_additions[user_id]
            await message.reply(
                "❌ **Erro ao verificar permissões.** Por favor, tente novamente mais tarde.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        if not admin_verified:
            # Limpar transação pendente se não for admin
            if user_id in pending_card_additions:
                del pending_card_additions[user_id]
            await message.reply(
                "🚫 **Acesso negado!** Somente administradores podem usar este comando.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Ensure the command is a reply to a message
        if not message.reply_to_message:
            if user_id in pending_card_additions:
                del pending_card_additions[user_id]
            await message.reply(
                "❗ **Erro:** Responda a uma mensagem contendo a imagem ou o arquivo do card e a legenda.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Extract the image and convert if necessary
        photo_file_id = None
        try:
            if message.reply_to_message.photo:
                photo_file_id = await ensure_photo_file_id(message.bot, message.reply_to_message.photo[-1], force_aspect_ratio=True)
            elif message.reply_to_message.document:
                # Check if the document is an image
                document = message.reply_to_message.document
                valid_extensions = {".jpg", ".jpeg", ".png"}
                if not any(document.file_name.lower().endswith(ext) for ext in valid_extensions):
                    if user_id in pending_card_additions:
                        del pending_card_additions[user_id]
                    await message.reply(
                        "❗ **Erro:** O arquivo enviado não é uma imagem válida. Apenas formatos `.jpg`, `.jpeg` e `.png` são aceitos.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    return
                photo_file_id = await ensure_photo_file_id(message.bot, document, force_aspect_ratio=True)
            else:
                if user_id in pending_card_additions:
                    del pending_card_additions[user_id]
                await message.reply(
                    "❗ **Erro:** A mensagem respondida deve conter uma imagem ou um arquivo de imagem válido.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
        except Exception as img_err:
            logger.error(f"Erro ao processar imagem: {str(img_err)}")
            if user_id in pending_card_additions:
                del pending_card_additions[user_id]
            await message.reply(
                f"❌ **Erro ao processar imagem:** {str(img_err)}",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Garantir que temos um file_id válido antes de continuar
        if not photo_file_id:
            if user_id in pending_card_additions:
                del pending_card_additions[user_id]
            await message.reply(
                "❌ **Erro:** Não foi possível obter um ID válido para a imagem.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Ensure the replied message contains a caption
        if not message.reply_to_message.caption:
            if user_id in pending_card_additions:
                del pending_card_additions[user_id]
            await message.reply(
                "❗ **Erro:** A mensagem respondida deve conter uma legenda com os campos necessários.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Extract the caption
        caption = message.reply_to_message.caption

        # Parse the caption (e.g., "[nome do card] | [nome do grupo] | [nome da categoria] | [tag] | [raridade]")
        try:
            # Replace commas with pipes to standardize the delimiter
            caption = caption.replace(",", "|")
            parts = list(map(str.strip, caption.split("|")))

            # Ensure the required fields are present
            if len(parts) < 4:
                raise ValueError("Missing required fields in the caption.")

            card_name, group_name, category_name, rarity = parts[:4]
            tag_name = parts[4] if len(parts) > 4 else None  # Optional tag
        except ValueError:
            if user_id in pending_card_additions:
                del pending_card_additions[user_id]
            await message.reply(
                "⚠️ **Formato inválido!** A legenda deve estar no formato:\n"
                "`nome do card | nome do grupo | nome da categoria | raridade [| tag opcional]`\n"
                "⚠️ **Importante:**\n"
                "- Raridades permitidas: 🥇, 🥈, 🥉 (para cards normais) e 💎 (para cards de eventos).",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Validate rarity
        allowed_rarities = {"🥇", "🥈", "🥉", "💎"}
        if rarity not in allowed_rarities:
            if user_id in pending_card_additions:
                del pending_card_additions[user_id]
            await message.reply(
                f"❌ **Erro:** A raridade '{rarity}' é inválida.\n"
                f"Por favor, use apenas um destes emojis para a raridade: 🥇, 🥈, 🥉 e 💎.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Primeiro, verificar por duplicatas (sem iniciar uma transação ainda)
        try:
            duplicate_card = None
            async with get_session() as check_session:
                # Verificar se já existe card com o mesmo nome (case insensitive)
                normalized_card_name = card_name.strip().lower()
                
                # Buscar possíveis duplicatas usando LOWER() para comparação case-insensitive
                duplicate_check = await check_session.execute(
                    select(Card).where(func.lower(Card.name) == normalized_card_name)
                )
                duplicate_card = duplicate_check.scalars().first()
            
            if duplicate_card:
                if user_id in pending_card_additions:
                    del pending_card_additions[user_id]
                await message.reply(
                    f"❌ **Erro:** Um card com nome similar já existe no sistema.\n"
                    f"• Nome existente: `{duplicate_card.name}` (ID: {duplicate_card.id})\n"
                    f"• Nome tentando adicionar: `{card_name}`\n\n"
                    f"Por favor, use um nome diferente para este card.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
        except Exception as check_err:
            logger.error(f"Erro ao verificar duplicatas: {str(check_err)}")
            if user_id in pending_card_additions:
                del pending_card_additions[user_id]
            await message.reply(
                f"❌ **Erro ao verificar duplicatas:** {str(check_err)}",
                parse_mode=ParseMode.MARKDOWN
            )
            return
                
        # Agora salvar o card no banco de dados em uma única transação
        try:
            card_id = None
            card_name_final = card_name
            
            # Abrir uma nova sessão especificamente para adicionar o card
            async with get_session() as session:
                # Iniciar uma transação explícita
                async with session.begin():
                    # Ensure the category exists
                    result = await session.execute(select(Category).where(Category.name == category_name))
                    category = result.scalars().first()
                    if not category:
                        category = Category(name=category_name)
                        session.add(category)
                        await session.flush()

                    # Ensure the group exists
                    result = await session.execute(
                        select(Group).where(Group.name == group_name, Group.category_id == category.id)
                    )
                    group = result.scalars().first()
                    if not group:
                        group = Group(name=group_name, category_id=category.id)
                        session.add(group)
                        await session.flush()

                    # Ensure the tag exists (if provided)
                    tag = None
                    if tag_name:
                        result = await session.execute(select(Tag).where(Tag.name == tag_name))
                        tag = result.scalars().first()
                        if not tag:
                            tag = Tag(name=tag_name)
                            session.add(tag)
                            await session.flush()

                    # Criar o novo card
                    new_card = Card(
                        name=card_name,
                        rarity=rarity,
                        image_file_id=photo_file_id,
                        group_id=group.id
                    )
                    session.add(new_card)
                    
                    # Aguardar o flush para ter o ID disponível
                    await session.flush()
                    card_id = new_card.id
                    
                    # Associate the card with the tag (if provided)
                    if tag:
                        await session.execute(card_tags.insert().values(card_id=new_card.id, tag_id=tag.id))

            # Limpar transação pendente após sucesso
            if user_id in pending_card_additions:
                del pending_card_additions[user_id]

            # Success message after transaction is committed
            await message.reply(
                f"✅ **Sucesso!** O card '{card_name_final}' (ID: {card_id}) foi adicionado ao sistema! 🃏✨",
                parse_mode=ParseMode.MARKDOWN
            )
            logger.info(f"Card added successfully: {card_name_final} (ID: {card_id})")

        except (IntegrityError, InvalidRequestError) as db_err:
            logger.error(f"Database error while adding card '{card_name}': {str(db_err)}")
            if user_id in pending_card_additions:
                del pending_card_additions[user_id]
            await message.reply(
                "❌ **Erro de banco de dados:** Ocorreu um problema ao salvar o card.\n"
                f"Detalhes: `{str(db_err)[:200]}`",
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Unexpected error while adding card '{card_name}': {str(e)}", exc_info=True)
            if user_id in pending_card_additions:
                del pending_card_additions[user_id]
            await message.reply(
                "❌ **Erro interno:** Não foi possível adicionar o card.\n"
                f"Detalhes: `{str(e)[:200]}`",
                parse_mode=ParseMode.MARKDOWN
            )

    except Exception as global_err:
        logger.error(f"Global error in add_card: {str(global_err)}", exc_info=True)
        # Limpar transação pendente em caso de erro global
        if user_id in pending_card_additions:
            del pending_card_additions[user_id]
        await message.reply(
            "❌ **Erro crítico:** Ocorreu um problema inesperado.\n"
            f"Detalhes: `{str(global_err)[:200]}`",
            parse_mode=ParseMode.MARKDOWN
        )

def cleanup_pending_transactions():
    """Remove transações pendentes antigas do dicionário"""
    current_time = time.time()
    cleaned = 0
    for user_id in list(pending_card_additions.keys()):
        if current_time - pending_card_additions[user_id] > TRANSACTION_TIMEOUT:
            del pending_card_additions[user_id]
            cleaned += 1
    
    if cleaned > 0:
        logger.info(f"Limpeza de transações: {cleaned} transações expiradas removidas")

# Função para limpeza periódica das transações - será chamada pelo scheduler
async def scheduled_cleanup():
    """Limpa periodicamente as transações pendentes"""
    while True:
        try:
            cleanup_pending_transactions()
        except Exception as e:
            logger.error(f"Erro durante limpeza programada: {str(e)}")
        
        # Esperar 60 segundos antes da próxima verificação
        await asyncio.sleep(60)