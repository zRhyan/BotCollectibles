from aiogram import Router, types, F
from aiogram.filters import Command, CommandObject
from aiogram.enums import ParseMode
from aiogram.types import Message

router = Router()

@router.message(Command("fileid"))
async def enviar_fileid(message: Message):
    replied = message.reply_to_message
    
    # Verificar se estamos em um grupo
    is_group = message.chat.type in ["group", "supergroup"]
    
    if not replied:
        await message.reply("Por favor, responda a uma mensagem que contenha uma imagem.")
        return
    
    try:
        # Caso 1: imagem padrão (tipo "foto")
        if replied.photo:
            photo = replied.photo[-1]  # Pegue a maior resolução
            file_id = photo.file_id
            await message.reply(f"file_id da imagem (photo):\n<code>{file_id}</code>", parse_mode=ParseMode.HTML)
            return
        
        # Caso 2: imagem enviada como arquivo (document)
        if replied.document and replied.document.mime_type and replied.document.mime_type.startswith("image/"):
            file_id = replied.document.file_id
            await message.reply(f"file_id da imagem (document):\n<code>{file_id}</code>", parse_mode=ParseMode.HTML)
            return
        
        # Adicionar mais casos se necessário (stickers, etc.)
        if replied.sticker:
            file_id = replied.sticker.file_id
            await message.reply(f"file_id do sticker:\n<code>{file_id}</code>", parse_mode=ParseMode.HTML)
            return
            
        await message.reply("A mensagem respondida não contém uma imagem válida (foto ou imagem enviada como arquivo).")
    
    except Exception as e:
        # Log do erro para debug
        print(f"Erro ao processar comando fileid: {e}")
        
        # Em caso de erro, enviar uma mensagem mais genérica
        if is_group:
            await message.reply(f"Erro ao processar a imagem. Detalhes: {str(e)}")
        else:
            await message.reply("Ocorreu um erro ao processar a imagem. Tente novamente ou contate o desenvolvedor.")