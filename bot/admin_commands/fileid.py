from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import Message

router = Router()

@router.message(Command("fileid"))
async def enviar_fileid(message: Message):
    # Verifica se está respondendo a alguma mensagem
    if not message.reply_to_message:
        await message.reply("Por favor, responda a uma imagem com o comando /fileid.")
        return

    replied = message.reply_to_message

    # Verifica se a mensagem respondida contém uma foto
    if replied.photo:
        photo = replied.photo[-1]  # Pega a imagem com maior resolução
        file_id = photo.file_id
        await message.reply(f"`{file_id}`", parse_mode="Markdown")
    else:
        await message.reply("A mensagem que você respondeu não contém uma imagem.")