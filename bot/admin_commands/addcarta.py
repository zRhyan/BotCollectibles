from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func
from database.models import User, Card, Group, Category, Tag, card_tags
from database.session import get_session
from bot.utils.image_utils import ensure_photo_file_id
import logging
import re
import asyncio
import time

# Configure logger
logger = logging.getLogger(__name__)

router = Router()

# Dicionário para rastrear transações pendentes de adição de cards
# Formato: {user_id: timestamp}
pending_card_additions = {}

# Tempo máximo (em segundos) que uma transação pode ficar pendente
TRANSACTION_TIMEOUT = 300  # 5 minutos

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
            "Por favor, conclua o processo atual ou aguarde 5 minutos para tentar novamente.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Registrar a transação pendente
    pending_card_additions[user_id] = current_time
    
    # Check if the user is an admin
    async with get_session() as session:
        result = await session.execute(select(User).where(User.id == message.from_user.id))
        user = result.scalars().first()  # Alterado scalar_one_or_none() para scalars().first()

        if not user or user.is_admin == 0:
            await message.reply(
                "🚫 **Acesso negado!** Somente administradores podem usar este comando.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

    # Ensure the command is a reply to a message
    if not message.reply_to_message:
        await message.reply(
            "❗ **Erro:** Responda a uma mensagem contendo a imagem ou o arquivo do card e a legenda.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Extract the image and convert if necessary
    photo_file_id = None
    if message.reply_to_message.photo:
        photo_file_id = await ensure_photo_file_id(message.bot, message.reply_to_message.photo[-1], force_aspect_ratio=True)
    elif message.reply_to_message.document:
        # Check if the document is an image
        document = message.reply_to_message.document
        valid_extensions = {".jpg", ".jpeg", ".png"}
        if not any(document.file_name.lower().endswith(ext) for ext in valid_extensions):
            await message.reply(
                "❗ **Erro:** O arquivo enviado não é uma imagem válida. Apenas formatos `.jpg`, `.jpeg` e `.png` são aceitos.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        photo_file_id = await ensure_photo_file_id(message.bot, document, force_aspect_ratio=True)
    else:
        await message.reply(
            "❗ **Erro:** A mensagem respondida deve conter uma imagem ou um arquivo de imagem válido.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Garantir que temos um file_id válido antes de continuar
    if not photo_file_id:
        await message.reply(
            "❌ **Erro:** Não foi possível obter um ID válido para a imagem.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Ensure the replied message contains a caption
    if not message.reply_to_message.caption:
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
        await message.reply(
            f"❌ **Erro:** A raridade '{rarity}' é inválida.\n"
            f"Por favor, use apenas um destes emojis para a raridade: 🥇, 🥈, 🥉 e 💎.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Save the card in the database
    async with get_session() as session:
        # Verificações iniciais fora da transação 
        # Verificar se já existe card com o mesmo nome (case insensitive)
        normalized_card_name = card_name.strip().lower()
        
        # Buscar possíveis duplicatas usando LOWER() para comparação case-insensitive
        duplicate_check = await session.execute(
            select(Card).where(func.lower(Card.name) == normalized_card_name)
        )
        existing_card = duplicate_check.scalars().first()
        
        if existing_card:
            await message.reply(
                f"❌ **Erro:** Um card com nome similar já existe no sistema.\n"
                f"• Nome existente: `{existing_card.name}` (ID: {existing_card.id})\n"
                f"• Nome tentando adicionar: `{card_name}`\n\n"
                f"Por favor, use um nome diferente para este card.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
            
        # Iniciar transação clara e explícita
        try:
            # Começar transação explicitamente
            async with session.begin() as transaction:
                # Ensure the category exists
                result = await session.execute(select(Category).where(Category.name == category_name))
                category = result.scalars().first()  # Alterado scalar_one_or_none() para scalars().first()
                if not category:
                    category = Category(name=category_name)
                    session.add(category)
                    await session.flush()  # Ensure the category ID is available

                # Ensure the group exists
                result = await session.execute(select(Group).where(Group.name == group_name, Group.category_id == category.id))
                group = result.scalars().first()  # Alterado scalar_one_or_none() para scalars().first()
                if not group:
                    group = Group(name=group_name, category_id=category.id)
                    session.add(group)
                    await session.flush()  # Ensure the group ID is available

                # Ensure the tag exists (if provided)
                tag = None
                if tag_name:
                    result = await session.execute(select(Tag).where(Tag.name == tag_name))
                    tag = result.scalars().first()  # Alterado scalar_one_or_none() para scalars().first()
                    if not tag:
                        tag = Tag(name=tag_name)
                        session.add(tag)
                        await session.flush()  # Ensure the tag ID is available

                # Check if the card already exists
                result = await session.execute(select(Card).where(Card.name == card_name))
                existing_card = result.scalars().first()  # Alterado scalar_one_or_none() para scalars().first()
                if existing_card:
                    await message.reply(
                        "❌ **Erro:** Um card com este nome já existe no sistema.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    return

                # Log attempt
                logger.info(f"Attempting to add card: {card_name}")
                
                new_card = Card(
                    name=card_name,
                    rarity=rarity,
                    image_file_id=photo_file_id,  # Usar o file_id obtido anteriormente
                    group_id=group.id
                )
                session.add(new_card)
                
                # Aguardar o flush para ter o ID disponível
                await session.flush()
                
                # Log success
                logger.info(f"Card added successfully with ID: {new_card.id}")

                # Associate the card with the tag (if provided)
                if tag:
                    await session.execute(card_tags.insert().values(card_id=new_card.id, tag_id=tag.id))
                
                # A transação é confirmada automaticamente ao sair do bloco

            # Confirm success - fora da transação
            await message.reply(
                f"✅ **Sucesso!** O card '{card_name}' (ID: {new_card.id}) foi adicionado ao sistema! 🃏✨",
                parse_mode=ParseMode.MARKDOWN
            )

        except IntegrityError as e:
            # A transação é revertida automaticamente no caso de exceção
            logger.error(f"IntegrityError while adding card '{card_name}': {str(e)}")
            await message.reply(
                "❌ **Erro:** Ocorreu um problema ao salvar o card no banco de dados.",
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Unexpected error while adding card '{card_name}': {str(e)}")
            await message.reply(
                "❌ **Erro interno:** Não foi possível adicionar o card.",
                parse_mode=ParseMode.MARKDOWN
            )
        finally:
            # No final do processamento, remover o usuário da lista de transações pendentes
            if user_id in pending_card_additions:
                del pending_card_additions[user_id]

def cleanup_pending_transactions():
    """Remove transações pendentes antigas do dicionário"""
    current_time = time.time()
    for user_id in list(pending_card_additions.keys()):
        if current_time - pending_card_additions[user_id] > TRANSACTION_TIMEOUT:
            del pending_card_additions[user_id]
            logger.info(f"Transação de adição de card expirada para usuário {user_id}")

# Função para limpeza periódica das transações - será chamada pelo scheduler
async def scheduled_cleanup():
    """Limpa periodicamente as transações pendentes"""
    while True:
        try:
            cleanup_pending_transactions()
            logger.debug("Executada limpeza de transações pendentes")
        except Exception as e:
            logger.error(f"Erro durante limpeza programada: {str(e)}")
        
        # Esperar 60 segundos antes da próxima verificação
        await asyncio.sleep(60)