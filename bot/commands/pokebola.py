# commands/pokebola.py
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from sqlalchemy import select
from database.session import get_session
from database.models import Card, Group, Category, Tag

pokebola_router = Router()

@pokebola_router.message(Command(commands=["pokebola", "pb"]))
async def pokebola_command(message: types.Message):
    """
    Handles the /pokebola (or /pb) command.
    Expects one argument: either card ID or partial card name.
    Fetches the card, then sends its image + attributes.
    """
    args = message.get_args()
    if not args:
        await message.reply(
            "❗ **Erro:** Forneça o ID ou nome do card. Exemplo:\n"
            "`/pokebola 42` ou `/pokebola Pikachu`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    async with get_session() as session:
        # 1) Try to interpret args as an integer (ID); if not, treat it as a name
        if args.isdigit():
            # Query by ID
            card_id = int(args)
            card = await session.get(Card, card_id)
        else:
            # Query by partial name using ILIKE
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

        # 2) Fetch Group & Category
        group_result = await session.execute(
            select(Group).where(Group.id == card.group_id)
        )
        group = group_result.scalar_one_or_none()

        category = None
        if group:
            category_result = await session.execute(
                select(Category).where(Category.id == group.category_id)
            )
            category = category_result.scalar_one_or_none()

        # 3) Fetch Tags (assuming a many-to-many relationship)
        #    Adjust this query if your relationship differs.
        tags_result = await session.execute(
            select(Tag).join(Tag.cards).where(Tag.cards.any(Card.id == card.id))
        )
        tags_list = tags_result.scalars().all()
        tags_str = ", ".join(tag.name for tag in tags_list) if tags_list else "Nenhuma"

        # 4) Prepare caption
        category_name = category.name if category else "Desconhecida"
        group_name = group.name if group else "Desconhecido"

        caption = (
            f"🆔 **ID:** {card.id}\n"
            f"🃏 **Nome:** {card.name}\n"
            f"📂 **Categoria:** {category_name}\n"
            f"📁 **Grupo:** {group_name}\n"
            f"✨ **Raridade:** {card.rarity}\n"
            f"🏷️ **Tags:** {tags_str}"
        )

        # 5) Send the card image + caption
        #    Make sure Card.image_file_id is a valid Telegram file_id
        await message.answer_photo(
            photo=card.image_file_id,
            caption=caption,
            parse_mode=ParseMode.MARKDOWN
        )
