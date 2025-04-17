from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload
from database.models import User, Card, Group, Category, Tag, Inventory
from database.session import get_session
from bot.utils.image_utils import ensure_photo_file_id
import logging
import tempfile
import os
import io
from PIL import Image
from aiogram.types import FSInputFile

# Configure logger
logger = logging.getLogger(__name__)

router = Router()

async def convert_document_to_photo(bot, file_id, user_id):
    """
    Converte um documento em uma foto e retorna o novo file_id.
    
    Args:
        bot: Instância do bot
        file_id: ID do arquivo a ser convertido
        user_id: ID do usuário para enviar a foto temporária
        
    Returns:
        str: File ID da foto convertida ou None se falhar
    """
    try:
        # Verificar se é realmente um documento
        file_info = await bot.get_file(file_id)
        is_photo = 'photos' in file_info.file_path
        
        if is_photo:
            # Já é uma foto, não precisa converter
            return file_id
            
        # Baixar o arquivo
        file_content = await bot.download_file(file_info.file_path)
        
        # Garantir que é bytes
        if isinstance(file_content, io.BytesIO):
            file_content = file_content.getvalue()
        
        # Processar a imagem com PIL
        img = Image.open(io.BytesIO(file_content))
        
        # Calcular dimensões para proporção 3:4 se necessário
        current_ratio = img.width / img.height
        target_ratio = 3/4
        
        # Processar a imagem para corrigir proporção
        if abs(current_ratio - target_ratio) > 0.1:
            if current_ratio > target_ratio:  # Imagem muito larga
                new_width = int(img.height * target_ratio)
                left = (img.width - new_width) // 2
                img = img.crop((left, 0, left + new_width, img.height))
            else:  # Imagem muito alta
                new_height = int(img.width / target_ratio)
                top = (img.height - new_height) // 2
                img = img.crop((0, top, img.width, top + new_height))
        
        # Converter para RGB se necessário
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Salvar em arquivo temporário
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_file:
            temp_path = temp_file.name
            img.save(temp_path, format='JPEG', quality=95)
        
        try:
            # Enviar para o usuário e obter novo file_id
            result = await bot.send_photo(
                chat_id=user_id,
                photo=FSInputFile(temp_path),
                caption="🔄 Processando imagem..."
            )
            
            # Obter novo file_id e apagar a mensagem temporária
            if result and result.photo:
                new_file_id = result.photo[-1].file_id
                
                # Apagar mensagem temporária
                try:
                    await bot.delete_message(chat_id=user_id, message_id=result.message_id)
                except Exception as e:
                    logger.warning(f"Não foi possível remover mensagem temporária: {str(e)}")
                
                return new_file_id
            
            return None
            
        finally:
            # Limpar arquivo temporário
            try:
                os.unlink(temp_path)
            except Exception as e:
                logger.warning(f"Erro ao remover arquivo temporário: {str(e)}")
    
    except Exception as e:
        logger.error(f"Erro ao converter documento para foto: {str(e)}", exc_info=True)
        return None

@router.message(Command(commands=["pokebola", "pb"]))
async def pokebola_command(message: types.Message):
    """
    Comando para exibir informações sobre um card específico, baseado no ID ou nome.
    Uso: /pokebola <card_id ou nome>
    """
    # Extract the arguments
    text_parts = message.text.split(maxsplit=1)
    user_id = message.from_user.id
    
    if len(text_parts) < 2:
        await message.reply(
            "❗ **Erro:** Por favor, forneça um ID ou nome do card.\n"
            "Exemplo: `/pokebola 42` ou `/pokebola Pikachu`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    card_identifier = text_parts[1].strip()
    
    # Try to process as an ID first
    try:
        card_id = int(card_identifier)
        search_by_id = True
    except ValueError:
        # If not an integer, search by name
        card_id = None
        search_by_id = False
    
    try:
        async with get_session() as session:
            # Prepare the query
            query = select(Card).options(
                joinedload(Card.group).joinedload(Group.category),
                joinedload(Card.tags)
            )
            
            # Filter by ID or name
            if search_by_id:
                query = query.where(Card.id == card_id)
            else:
                query = query.where(Card.name.ilike(f"%{card_identifier}%"))
            
            result = await session.execute(query)
            card = result.unique().scalars().first()
            
            if not card:
                await message.reply(
                    f"❌ **Erro:** Nenhum card encontrado {'com o ID' if search_by_id else 'com o nome'} `{card_identifier}`.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            
            # Verificar se a carta está armazenada como documento e precisa ser convertida para foto
            try:
                file_info = await message.bot.get_file(card.image_file_id)
                is_photo = 'photos' in file_info.file_path
                
                # Se não for foto, converter para foto
                if not is_photo:
                    logger.info(f"Convertendo imagem do card ID {card.id} de documento para foto")
                    
                    # Enviar mensagem de processamento
                    processing_msg = await message.reply(
                        "🔄 **Processando imagem...**\n"
                        "Convertendo para formato ideal, por favor aguarde.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    
                    # Converter documento para foto
                    new_file_id = await convert_document_to_photo(
                        bot=message.bot,
                        file_id=card.image_file_id,
                        user_id=user_id
                    )
                    
                    # Remover mensagem de processamento
                    try:
                        await processing_msg.delete()
                    except Exception as del_error:
                        logger.warning(f"Erro ao remover mensagem de processamento: {del_error}")
                    
                    if new_file_id:
                        # Atualizar o file_id no banco de dados
                        card.image_file_id = new_file_id
                        await session.commit()
                        logger.info(f"Card ID {card.id} atualizado com novo file_id")
                    else:
                        logger.warning(f"Falha ao converter imagem do card {card.id}")
            except Exception as e:
                logger.error(f"Erro ao verificar/converter formato de imagem do card {card.id}: {str(e)}")
                # Continuar com o file_id existente mesmo em caso de erro
            
            # Get the inventory count for this card for the current user
            inventory_query = await session.execute(
                select(Inventory)
                .where(Inventory.user_id == user_id, Inventory.card_id == card.id)
            )
            inventory_item = inventory_query.scalars().first()
            owned_count = inventory_item.quantity if inventory_item else 0
            
            # Prepare the caption
            group_name = card.group.name if card.group else "Grupo Desconhecido"
            category_name = card.group.category.name if card.group and card.group.category else "Categoria Desconhecida"
            rarity = card.rarity
            
            # Prepare tags text
            tags_text = ", ".join([tag.name for tag in card.tags]) if card.tags else "Nenhuma"
            
            # Send the card image with information
            caption = (
                f"📊 **Informações do Card** 📊\n"
                f"**ID:** `{card.id}`\n"
                f"**Nome:** {card.name}\n"
                f"**Grupo:** {group_name}\n"
                f"**Categoria:** {category_name}\n"
                f"**Raridade:** {rarity}\n"
                f"**Tags:** {tags_text}\n\n"
                f"**Você possui:** {owned_count} unidades"
            )
            
            # Se a conversão foi feita ou já era foto, podemos enviar normalmente
            try:
                await message.reply_photo(
                    photo=card.image_file_id,
                    caption=caption,
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as photo_error:
                # Se ainda ocorrer erro, tentar enviar como documento com caption
                logger.error(f"Erro ao enviar como foto: {str(photo_error)}")
                
                await message.reply(
                    caption,
                    parse_mode=ParseMode.MARKDOWN
                )
                
                # E enviar imagem separadamente como documento
                await message.reply_document(
                    document=card.image_file_id,
                    caption=f"ID {card.id}: {card.name}"
                )
    
    except Exception as e:
        logger.error(f"Error in pokebola command: {str(e)}", exc_info=True)
        await message.reply(
            "❌ **Erro ao processar o comando:** Ocorreu um problema ao buscar informações do card.\n"
            f"Detalhes: `{str(e)[:100]}`",
            parse_mode=ParseMode.MARKDOWN
        )