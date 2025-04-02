from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import Message

router = Router()

@router.message(Command("fileid"))
async def enviar_fileid(message: Message):
    replied = message.reply_to_message

    if not replied:
        await message.reply("Por favor, responda a uma mensagem que contenha uma imagem.")
        return

    # Caso 1: imagem padrão (tipo "foto")
    if replied.photo:
        photo = replied.photo[-1]
        file_id = photo.file_id
        await message.reply(f"file_id da imagem (photo):\n`{file_id}`", parse_mode=ParseMode.MARKDOWN)
        return

    # Caso 2: imagem enviada como arquivo (document)
    if replied.document and replied.document.mime_type and replied.document.mime_type.startswith("image/"):
        file_id = replied.document.file_id
        await message.reply(f"file_id da imagem (document):\n`{file_id}`", parse_mode=ParseMode.MARKDOWN)
        return

    await message.reply("A mensagem respondida não contém uma imagem válida (foto ou imagem enviada como arquivo).")