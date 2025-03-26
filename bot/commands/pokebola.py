from aiogram import Router, types
from sqlalchemy.orm import Session
from database.models import Card, Group, Category, Tag
from bot import bot  # Assuming bot instance is initialized elsewhere

router = Router()

@router.message(commands=["pokebola", "pb"])
async def pokebola_command(message: types.Message, session: Session):
    args = message.get_args()
    if not args:
        await message.reply("Please provide the ID or name of the card.")
        return

    # Query card by ID or name
    card = session.query(Card).filter(
        (Card.id == args) | (Card.name.ilike(f"%{args}%"))
    ).first()

    if not card:
        await message.reply("Card not found.")
        return

    # Fetch related details
    group = session.query(Group).filter(Group.id == card.group_id).first()
    category = session.query(Category).filter(Category.id == group.category_id).first()
    tags = ", ".join(tag.name for tag in card.tags)

    # Prepare caption
    caption = (
        f"ID: {card.id}\n"
        f"Name: {card.name}\n"
        f"Category: {category.name}\n"
        f"Group: {group.name}\n"
        f"Rarity: {card.rarity}\n"
        f"Tags: {tags if tags else 'None'}"
    )

    # Send card image with caption
    await bot.send_photo(chat_id=message.chat.id, photo=card.image_file_id, caption=caption)
