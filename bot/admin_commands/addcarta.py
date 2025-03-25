from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode  # Added import
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from database.models import Card
from database.session import get_session

router = Router()

# List of admin user IDs (replace with actual admin IDs)
ADMIN_IDS = [123456789, 987654321]

@router.message(Command(commands=["addcarta", "add"]))
async def add_card(message: types.Message):
    # Check if the user is an admin
    if message.from_user.id not in ADMIN_IDS:
        await message.reply("🚫 **Acesso negado!** Somente administradores podem usar este comando.", 
        parse_mode=ParseMode.MARKDOWN)
        return

    # Ensure the command is a reply to a message
    if not message.reply_to_message:
        await message.reply("❗ **Erro:** Responda a uma mensagem contendo a imagem e a legenda do card.", 
        parse_mode=ParseMode.MARKDOWN)
        return

    # Ensure the replied message contains an image
    if not message.reply_to_message.photo:
        await message.reply("❗ **Erro:** A mensagem respondida deve conter uma imagem do card.", 
        parse_mode=ParseMode.MARKDOWN)
        return

    # Ensure the replied message contains a caption
    if not message.reply_to_message.caption:
        await message.reply("❗ **Erro:** A mensagem respondida deve conter uma legenda com o nome e a raridade do card.", 
        parse_mode=ParseMode.MARKDOWN)
        return

    # Extract image file ID and caption
    photo_file_id = message.reply_to_message.photo[-1].file_id  # Get the highest resolution image
    caption = message.reply_to_message.caption

    # Parse the caption (e.g., "Card Name | Rarity")
    try:
        card_name, rarity = map(str.strip, caption.split("|"))
    except ValueError:
        await message.reply("⚠️ **Formato inválido!** A legenda deve estar no formato: `Nome do Card | Raridade`.", 
        parse_mode=ParseMode.MARKDOWN)
        return

    # Save the card in the database
    async with get_session() as session: # Use get_session for session management
        # Check if the card already exists
        existing_card = await session.execute(select(Card).where(Card.name == card_name))
        if existing_card.scalar_one_or_none():
            await message.reply("Um card com este nome já existe no sistema.", 
            parse_mode=ParseMode.MARKDOWN)
            return

        # Add the new card
        new_card = Card(name=card_name, rarity=rarity, image_file_id=photo_file_id)
        session.add(new_card)
        await session.commit()

    # Confirm success
    await message.reply(f"✅ **Sucesso!** O card '{card_name}' foi adicionado ao sistema! 🃏✨", 
    parse_mode=ParseMode.MARKDOWN)