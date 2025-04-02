from aiogram import Router
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import Message
from database.session import get_session
from database.models import User
from sqlalchemy.future import select

router = Router()

@router.message(Command("fileid"))
async def enviar_fileid(message: Message):
    replied = message.reply_to_message
    
    # Verificar se estamos em um grupo
    is_group = message.chat.type in ["group", "supergroup"]
    
    # Check if the user is an admin
    async with get_session() as session:
        result = await session.execute(select(User).where(User.id == message.from_user.id))
        user = result.scalar_one_or_none()

        if not user or user.is_admin == 0:
            await message.reply(
                "🚫 **Acesso negado!** Somente administradores podem usar este comando.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

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