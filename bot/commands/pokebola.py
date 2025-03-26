from aiogram import Router, types
from aiogram.filters import Command
from sqlalchemy.future import select
from database.models import Card, Group, Category, Tag

router = Router()

@router.message(Command(commands=["pokebola", "pb"]))
async def pokebola_command(message: types.Message, session):
    args = message.get_args()
    if not args:
        await message.reply("❗ **Erro:** Forneça o ID ou nome do card.", parse_mode=types.ParseMode.MARKDOWN)
        return

    # Query card by ID or name
    result = await session.execute(
        select(Card).where((Card.id == args) | (Card.name.ilike(f"%{args}%")))
    )
    card = result.scalar_one_or_none()

    if not card:
        await message.reply("❌ **Erro:** Card não encontrado.", parse_mode=types.ParseMode.MARKDOWN)
        return

    # Fetch related details
    group_result = await session.execute(select(Group).where(Group.id == card.group_id))
    group = group_result.scalar_one_or_none()

    category_result = await session.execute(select(Category).where(Category.id == group.category_id))
    category = category_result.scalar_one_or_none()

    tags_result = await session.execute(select(Tag).join(card.tags))
    tags = ", ".join(tag.name for tag in tags_result.scalars())

    # Prepare caption
    caption = (
        f"🆔 **ID:** {card.id}\n"
        f"🃏 **Nome:** {card.name}\n"
        f"📂 **Categoria:** {category.name}\n"
        f"📁 **Grupo:** {group.name}\n"
        f"✨ **Raridade:** {card.rarity}\n"
        f"🏷️ **Tags:** {tags if tags else 'Nenhuma'}"
    )

    # Send card image with caption
    await message.answer_photo(photo=card.image_file_id, caption=caption, parse_mode=types.ParseMode.MARKDOWN)