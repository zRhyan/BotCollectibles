from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload
from database.models import User, Card, Group, Category, Tag, Inventory
from database.session import get_session
from bot.utils.image_utils import ensure_photo_file_id, update_card_image_in_db
import logging

# Configure logger
logger = logging.getLogger(__name__)

router = Router()

@router.message(Command(commands=["pokebola"]))
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
                
                # Se não for foto, atualizar a imagem para o formato de foto
                if not is_photo:
                    logger.info(f"Convertendo imagem do card ID {card.id} de documento para foto")
                    
                    # Enviar mensagem de processamento
                    processing_msg = await message.reply(
                        "🔄 **Processando imagem...**\n"
                        "Convertendo para formato ideal, por favor aguarde.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    
                    # Atualizar a imagem no banco de dados usando a função existente
                    success, error = await update_card_image_in_db(
                        bot=message.bot,
                        card_id=card.id,
                        user_id=user_id  # Usamos o ID do usuário que solicitou a carta
                    )
                    
                    # Remover mensagem de processamento
                    try:
                        await processing_msg.delete()
                    except Exception as del_error:
                        logger.warning(f"Erro ao remover mensagem de processamento: {del_error}")
                    
                    if not success:
                        logger.warning(f"Falha ao converter imagem do card {card.id}: {error}")
                    else:
                        # Atualizar o card local para o restante do processamento
                        # Buscar o card novamente para obter o file_id atualizado
                        result = await session.execute(
                            select(Card).where(Card.id == card.id)
                        )
                        card = result.scalar_one()
                        logger.info(f"Card ID {card.id} atualizado com novo file_id")
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
            
            # Usar sempre o file_id mais recente do card (que pode ter sido atualizado)
            await message.reply_photo(
                photo=card.image_file_id,
                caption=caption,
                parse_mode=ParseMode.MARKDOWN
            )
    
    except Exception as e:
        logger.error(f"Error in pokebola command: {str(e)}", exc_info=True)
        await message.reply(
            "❌ **Erro ao processar o comando:** Ocorreu um problema ao buscar informações do card.\n"
            f"Detalhes: `{str(e)[:100]}`",
            parse_mode=ParseMode.MARKDOWN
        )