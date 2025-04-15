from aiogram import Bot
from aiogram.types import Message, Document, PhotoSize

async def ensure_photo_file_id(bot: Bot, document: Document | PhotoSize) -> str:
    """
    Ensures we have a photo file_id, converting from document if necessary.
    Returns the photo file_id that can be used with send_photo.
    """
    if isinstance(document, PhotoSize):
        return document.file_id
        
    # If it's a document, we need to convert it
    file = await bot.get_file(document.file_id)
    downloaded_file = await bot.download_file(file.file_path)
    
    # Send as photo and get the file_id
    message = await bot.send_photo(
        chat_id="-1",  # Temporary chat_id, message won't be delivered
        photo=downloaded_file,
        disable_notification=True
    )
    
    # Get the file_id of the photo version
    photo_file_id = message.photo[-1].file_id
    
    try:
        # Clean up the temporary message
        await message.delete()
    except:
        pass
        
    return photo_file_id
