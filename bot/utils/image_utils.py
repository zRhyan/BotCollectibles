from PIL import Image
import io
import uuid
import os
import logging
from aiogram import Bot
from aiogram.types import Document, BufferedInputFile, InputFile

# Configurar logger
logger = logging.getLogger(__name__)

# ID do usuário que receberá as imagens temporárias para obtenção do file_id
ADMIN_USERNAME = "@zRhYaN"
ADMIN_CHAT_ID = 1686075980  # ID correspondente ao @zRhYaN

async def ensure_photo_file_id(bot: Bot, document: Document, force_aspect_ratio: bool = False) -> str:
    """
    Ensures a document is converted to a photo with correct aspect ratio if needed.
    Args:
        bot: Bot instance
        document: Document to convert
        force_aspect_ratio: If True, forces 3:4 aspect ratio
    Returns:
        str: File ID of the processed photo with correct aspect ratio
    """
    try:
        # Download the file
        file = await bot.get_file(document.file_id)
        file_content = await bot.download_file(file.file_path)
        
        # Check if file_content is a BytesIO object and convert to bytes if needed
        if isinstance(file_content, io.BytesIO):
            file_content = file_content.getvalue()
        
        # Open image with PIL
        img = Image.open(io.BytesIO(file_content))
        
        # Se não precisamos forçar proporção, apenas retornamos o file_id original
        if not force_aspect_ratio:
            return document.file_id
        
        # Calculate target dimensions for 3:4 ratio
        current_ratio = img.width / img.height
        target_ratio = 3/4
        
        # Se a proporção já está correta (ou próxima o suficiente), retorne o file_id original
        if abs(current_ratio - target_ratio) <= 0.01:
            return document.file_id
            
        logger.info(f"Ajustando proporção da imagem para 3:4. Proporção atual: {current_ratio}")
        
        # Process the image to correct aspect ratio
        if current_ratio > target_ratio:  # Image is too wide
            new_width = int(img.height * target_ratio)
            left = (img.width - new_width) // 2
            img = img.crop((left, 0, left + new_width, img.height))
        else:  # Image is too tall
            new_height = int(img.width / target_ratio)
            top = (img.height - new_height) // 2
            img = img.crop((0, top, img.width, top + new_height))
        
        # Convert to RGB if needed
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Save to bytes
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='JPEG', quality=95)
        img_byte_arr.seek(0)
        img_bytes = img_byte_arr.getvalue()
        
        # Enviar para o admin (@zRhYaN) em vez do próprio bot
        try:
            logger.info(f"Enviando imagem processada para {ADMIN_USERNAME} para obter file_id")
            result = await bot.send_photo(
                chat_id=ADMIN_CHAT_ID,
                photo=BufferedInputFile(img_bytes, filename='processed_card.jpg'),
                caption=f"🔄 Imagem processada para proporção 3:4\n⚠️ Esta mensagem pode ser apagada após processamento"
            )
            
            # Obter o file_id da imagem processada
            if result and result.photo:
                new_file_id = result.photo[-1].file_id
                logger.info(f"Novo file_id obtido com sucesso: {new_file_id[:10]}...")
                return new_file_id
            else:
                logger.warning("Não foi possível obter o file_id da imagem processada")
        except Exception as e:
            logger.error(f"Erro ao enviar imagem para admin: {str(e)}")
        
        # Fallback para o file_id original caso não seja possível enviar para o admin
        return document.file_id

    except Exception as e:
        logger.error(f"Erro ao processar imagem: {str(e)}")
        # Fallback para o file_id original em caso de erro
        return document.file_id
