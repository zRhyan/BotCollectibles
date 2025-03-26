# commands/pokebola.py
from aiogram import Router, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from sqlalchemy import select
from database.session import get_session
from database.models import Card, Group, Category, Tag

router = Router()

@router.message(Command(commands=["pokebola", "pb"]))
async def pokebola_command(message: types.Message):
    """
    Handles the /pokebola (or /pb) command in Aiogram v3.
    Expects one argument: either card ID or partial card name.
    Fetches the card, then sends its image + attributes.
    """
    # Parse args manually (Aiogram v3 no longer has message.get_args())
    text_parts = message.text.split(maxsplit=1)
    # e.g. ['/pokebola', 'black hole'] or ['/pb', '42']

    if len(text_parts) < 2:
        await message.reply(
            "❗ **Erro:** Forneça o ID ou nome do card. Exemplo:\n"
            "`/pokebola 42` ou `/pokebola Pikachu`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    args = text_parts[1].strip()

    async with get_session() as session:
        # 1) Try numeric ID
        if args.isdigit():
            card_id = int(args)
            card = await session.get(Card, card_id)
        else:
            # 2) Query by partial name
            result = await session.execute(
                select(Card).where(Card.name.ilike(f"%{args}%"))
            )
            card = result.scalar_one_or_none()

        if not card:
            await message.reply(
                "❌ **Erro:** Card não encontrado.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Fetch group and category if they exist
        group = None
        if card.group_id:
            group_result = await session.execute(
                select(Group).where(Group.id == card.group_id)
            )
            group = group_result.scalar_one_or_none()

        category = None
        if group and group.category_id:
            category_result = await session.execute(
                select(Category).where(Category.id == group.category_id)
            )
            category = category_result.scalar_one_or_none()

        # Fetch tags (assuming many-to-many)
        tags_result = await session.execute(
            select(Tag).join(Tag.cards).where(Tag.cards.any(Card.id == card.id))
        )
        tags_list = tags_result.scalars().all()
        tags_str = ", ".join(tag.name for tag in tags_list) if tags_list else "Nenhuma"

        category_name = category.name if category else "Desconhecida"
        group_name = group.name if group else "Desconhecido"

        # Build caption
        caption = (
            f"🆔 **ID:** {card.id}\n"
            f"🃏 **Nome:** {card.name}\n"
            f"📂 **Categoria:** {category_name}\n"
            f"📁 **Grupo:** {group_name}\n"
            f"✨ **Raridade:** {card.rarity}\n"
            f"🏷️ **Tags:** {tags_str}"
        )

        # Send photo + caption
        await message.answer_photo(
            photo=card.image_file_id,  # must be a valid Telegram file_id
            caption=caption,
            parse_mode=ParseMode.MARKDOWN
        )
