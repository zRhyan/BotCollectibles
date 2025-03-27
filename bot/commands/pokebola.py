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
    Handles the /pokebola (or /pb) command.
    Expects one argument: either card ID or partial card name.
    Fetches the card, then sends its image and attributes.
    """
    # Parse arguments
    text_parts = message.text.split(maxsplit=1)
    if len(text_parts) < 2:
        await message.reply(
            "❗ **Erro:** Forneça o ID ou nome do card. Exemplo:\n"
            "`/pokebola 42` ou `/pokebola Pikachu`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    args = text_parts[1].strip()

    async with get_session() as session:
        # Query the card by ID or name
        card = None
        if args.isdigit():
            card_id = int(args)
            card = await session.get(Card, card_id)
        else:
            result = await session.execute(
                select(Card).where(Card.name.ilike(f"%{args}%"))
            )
            cards = result.scalars().all()

            if len(cards) == 0:
                await message.reply(
                    "❌ **Erro:** Nenhum card encontrado com o ID ou nome fornecido.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            elif len(cards) > 1:
                await message.reply(
                    "⚠️ **Erro:** Mais de um card encontrado com um nome similar. Tente utilizar o ID.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

            card = cards[0]

        # Fetch related details
        group = card.group
        category = group.category if group else None

        # Fetch tags (deduplicated)
        tags_result = await session.execute(
            select(Tag).join(Tag.cards).where(Tag.cards.any(Card.id == card.id))
        )
        tags = {tag.name for tag in tags_result.scalars()}  # Use a set to ensure uniqueness
        tags_str = ", ".join(tags) if tags else "Nenhuma"

        # Prepare the response
        caption = (
            f"🆔 **ID:** {card.id}\n"
            f"🃏 **Nome:** {card.name}\n"
            f"📂 **Categoria:** {category.name if category else 'Nenhuma'}\n"
            f"📁 **Grupo:** {group.name if group else 'Nenhum'}\n"
            f"✨ **Raridade:** {card.rarity}\n"
            f"🏷️ **Tags:** {tags_str}"
        )

        # Send the card image with the caption
        await message.answer_photo(
            photo=card.image_file_id,
            caption=caption,
            parse_mode=ParseMode.MARKDOWN
        )