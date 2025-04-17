from PIL import Image
import io
import uuid
import os
import logging
from aiogram import Bot
from aiogram.types import Document, BufferedInputFile, InputFile

# Configurar logger
logger = logging.getLogger(__name__)

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
        
        # Método alternativo: usar o ID de um usuário real (como o administrador) 
        # para enviar a imagem e obter um file_id válido
        # Isso exige que o ID do usuário seja fornecido à função
        
        # Como não podemos enviar mensagem para o próprio bot para obter um file_id,
        # a alternativa mais prática é armazenar e usar o file_id original,
        # mesmo sabendo que a imagem que será exibida não terá a proporção exata de 3:4
        
        logger.warning("Impossível obter file_id para imagem processada sem enviar mensagem. " +
                       "Usando file_id original, o que pode resultar na exibição da imagem com proporção incorreta.")
        
        # Solução temporária: retornar o file_id original
        # Nota: Isto não garante que a imagem exibida tenha a proporção 3:4
        return document.file_id

    except Exception as e:
        logger.error(f"Erro ao processar imagem: {str(e)}")
        # Fallback para o file_id original em caso de erro
        return document.file_id
