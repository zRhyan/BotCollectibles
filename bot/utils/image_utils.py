from PIL import Image
import io
import logging
import tempfile
import os
from aiogram import Bot
from aiogram.types import Document, FSInputFile, PhotoSize, Message
from typing import Union, Optional, Tuple

# Configurar logger
logger = logging.getLogger(__name__)

# ID do usuário que receberá as imagens temporárias para obtenção do file_id
ADMIN_USERNAME = "@zRhYaN"
ADMIN_CHAT_ID = 1686075980  # ID correspondente ao @zRhYaN

async def ensure_photo_file_id(
    bot: Bot, 
    content: Union[Document, PhotoSize, str], 
    user_id: int,
    force_aspect_ratio: bool = True,
    mode: str = "lookup"
) -> str:
    """
    Garante que um documento ou file_id seja convertido para photo com proporção 3:4.
    
    Args:
        bot: Instância do bot
        content: Documento, PhotoSize, ou file_id para converter
        user_id: ID do usuário para enviar a foto temporária e obter novo file_id
        force_aspect_ratio: Se True, força proporção 3:4
        mode: "input" quando o conteúdo vem diretamente de uma mensagem do usuário,
              "lookup" quando é apenas o file_id existente no banco sem mensagem associada
        
    Returns:
        str: File ID da foto processada com proporção correta
    """
    try:
        file_id = None
        is_already_photo = False
        
        # Determinar o file_id e se já é uma foto
        if isinstance(content, str):
            file_id = content
            # Verificar se o file_id é de uma foto ou documento
            try:
                file_info = await bot.get_file(file_id)
                is_already_photo = 'photos' in file_info.file_path
            except Exception as e:
                logger.error(f"Erro ao obter informações do arquivo: {str(e)}")
                return file_id
        
        elif isinstance(content, PhotoSize):
            file_id = content.file_id
            is_already_photo = True
            
        elif isinstance(content, Document):
            file_id = content.file_id
            is_already_photo = False
            
        else:
            logger.error(f"Tipo de conteúdo não suportado: {type(content)}")
            return None
        
        # Se já é uma foto e não precisamos forçar proporção, apenas retornamos
        if is_already_photo and not force_aspect_ratio:
            return file_id
        
        # Se já é uma foto e proporção já está correta, retornamos o original
        if is_already_photo:
            # Verificar proporção atual
            try:
                file = await bot.get_file(file_id)
                file_content = await bot.download_file(file.file_path)
                
                # Abrir a imagem com PIL
                img = Image.open(io.BytesIO(file_content))
                current_ratio = img.width / img.height
                target_ratio = 3/4
                
                # Se a proporção já está próxima de 3:4, não precisamos ajustar
                if abs(current_ratio - target_ratio) <= 0.1:
                    return file_id
            except Exception as e:
                logger.warning(f"Erro ao verificar proporção de imagem: {str(e)}")
                # Em caso de erro, retornamos o file_id original
                return file_id
        
        # Baixar o arquivo
        file = await bot.get_file(file_id)
        file_content = await bot.download_file(file.file_path)
        
        # Garantir que é bytes
        if isinstance(file_content, io.BytesIO):
            file_content = file_content.getvalue()
        
        # Abrir imagem com PIL
        img = Image.open(io.BytesIO(file_content))
        
        # Calcular dimensões alvo para proporção 3:4
        current_ratio = img.width / img.height
        target_ratio = 3/4
        
        logger.info(f"Ajustando proporção da imagem para 3:4. Proporção atual: {current_ratio}")
        
        # Processar a imagem para corrigir proporção
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
            # Enviar para o usuário (especificado por user_id) e obter novo file_id
            logger.info(f"Enviando imagem processada para usuário {user_id} para obter file_id")
            
            # Diferentes mensagens baseadas no modo
            caption = None
            if mode == "input":
                # No modo input, o usuário está enviando a imagem diretamente
                caption = "🔄 Processando imagem..."
            
            # Enviar a foto
            result = await bot.send_photo(
                chat_id=user_id,
                photo=FSInputFile(temp_path),
                caption=caption
            )
            
            # Obter novo file_id
            new_file_id = None
            if result and result.photo:
                new_file_id = result.photo[-1].file_id
                logger.info(f"Novo file_id obtido com sucesso: {new_file_id[:10]}...")
            
            # Apagar mensagem temporária apenas no modo lookup
            # (no modo input, mantemos para mostrar ao usuário)
            if mode == "lookup" and result:
                try:
                    await bot.delete_message(chat_id=user_id, message_id=result.message_id)
                    logger.info("Mensagem temporária removida")
                except Exception as e:
                    logger.warning(f"Não foi possível remover mensagem temporária: {str(e)}")
            
            # Retornar novo file_id ou o original em caso de falha
            return new_file_id or file_id
            
        finally:
            # Limpar arquivo temporário
            try:
                os.unlink(temp_path)
            except Exception as e:
                logger.warning(f"Erro ao remover arquivo temporário: {str(e)}")
    
    except Exception as e:
        logger.error(f"Erro ao processar imagem: {str(e)}", exc_info=True)
        return file_id if file_id else None


async def is_document_image(document: Document) -> bool:
    """
    Verifica se um documento é uma imagem baseado na extensão ou mime-type.
    
    Args:
        document: Objeto Document do aiogram
        
    Returns:
        bool: True se o documento for uma imagem, False caso contrário
    """
    if not document:
        return False
        
    # Verificar mime-type
    if document.mime_type and document.mime_type.startswith('image/'):
        return True
        
    # Verificar extensão
    if document.file_name:
        valid_extensions = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
        file_ext = os.path.splitext(document.file_name.lower())[1]
        return file_ext in valid_extensions
        
    return False


async def update_card_image_in_db(bot: Bot, card_id: int, user_id: int) -> Tuple[bool, Optional[str]]:
    """
    Atualiza a imagem de um card no banco de dados, convertendo de document para photo se necessário.
    
    Args:
        bot: Instância do bot
        card_id: ID do card a atualizar
        user_id: ID do usuário para enviar a foto temporária
        
    Returns:
        Tuple[bool, Optional[str]]: (sucesso, mensagem de erro)
    """
    from sqlalchemy.future import select
    from database.models import Card
    from database.session import get_session
    
    try:
        # Buscar card do banco
        async with get_session() as session:
            result = await session.execute(select(Card).where(Card.id == card_id))
            card = result.scalar_one_or_none()
            
            if not card:
                return False, f"Card ID {card_id} não encontrado"
            
            original_file_id = card.image_file_id
            
            # Verificar se precisa converter (se é documento ou proporção incorreta)
            try:
                file_info = await bot.get_file(original_file_id)
                is_photo = 'photos' in file_info.file_path
                
                if is_photo:
                    # Se já é foto, não precisamos converter
                    logger.info(f"Card ID {card_id} já possui uma imagem em formato photo")
                    return True, None
            except Exception as e:
                logger.error(f"Erro ao verificar arquivo do card {card_id}: {str(e)}")
                return False, f"Erro ao verificar arquivo: {str(e)}"
            
            # Converter para photo
            new_file_id = await ensure_photo_file_id(
                bot=bot,
                content=original_file_id,
                user_id=user_id,
                force_aspect_ratio=True
            )
            
            if not new_file_id or new_file_id == original_file_id:
                return False, "Não foi possível converter a imagem"
            
            # Atualizar no banco
            card.image_file_id = new_file_id
            await session.commit()
            
            logger.info(f"Imagem do card ID {card_id} atualizada com sucesso")
            return True, None
            
    except Exception as e:
        logger.error(f"Erro ao atualizar imagem do card {card_id}: {str(e)}", exc_info=True)
        return False, f"Erro interno: {str(e)}"
