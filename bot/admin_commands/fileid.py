from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode

router = Router()

@router.message(Command("fileid"))
async def capturar_file_id(message: types.Message):
    file_id = message.photo[-1].file_id
    await message.reply(f"file_id: `{file_id}`", parse_mode=ParseMode.MARKDOWN)