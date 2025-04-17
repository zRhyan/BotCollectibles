from PIL import Image
import io
from aiogram import Bot
from aiogram.types import Document, BufferedInputFile

async def ensure_photo_file_id(bot: Bot, document: Document, force_aspect_ratio: bool = False) -> str:
    """
    Ensures a document is converted to a photo with correct aspect ratio if needed.
    Args:
        bot: Bot instance
        document: Document to convert
        force_aspect_ratio: If True, forces 3:4 aspect ratio
    Returns:
        str: File ID of the photo
    """
    # Download the file
    file = await bot.get_file(document.file_id)
    file_content = await bot.download_file(file.file_path)
    
    # Check if file_content is a BytesIO object and convert to bytes if needed
    if isinstance(file_content, io.BytesIO):
        file_content = file_content.getvalue()
    
    # Open image with PIL
    img = Image.open(io.BytesIO(file_content))
    
    if force_aspect_ratio:
        # Calculate target dimensions for 3:4 ratio
        current_ratio = img.width / img.height
        target_ratio = 3/4
        
        if abs(current_ratio - target_ratio) > 0.01:  # If ratio is significantly different
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
    img.save(img_byte_arr, format='JPEG')
    img_bytes = img_byte_arr.getvalue()
    
    # Upload as photo using BufferedInputFile instead of FSInputFile
    result = await bot.send_photo(
        chat_id=bot.id,  # Send to bot itself
        photo=BufferedInputFile(img_bytes, filename='photo.jpg')
    )
    
    # Get and return the file_id of the uploaded photo
    return result.photo[-1].file_id
