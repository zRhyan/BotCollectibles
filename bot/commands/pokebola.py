from aiogram import Router, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from sqlalchemy import select
from database.session import get_session
from database.models import Card, Group, Category, Tag, Inventory
from sqlalchemy.orm import joinedload

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
        # Query the card by ID or name with eager loading
        card = None
        if args.isdigit():
            card_id = int(args)
            result = await session.execute(
                select(Card)
                .options(
                    joinedload(Card.group).joinedload(Group.category),  # Eager load group and category
                    joinedload(Card.tags)  # Eager load tags
                )
                .where(Card.id == card_id)
            )
            # Call unique() to remove duplicates from joined eager loads
            card = result.unique().scalar_one_or_none()
        else:
            result = await session.execute(
                select(Card)
                .options(
                    joinedload(Card.group).joinedload(Group.category),  # Eager load group and category
                    joinedload(Card.tags)  # Eager load tags
                )
                .where(Card.name.ilike(f"%{args}%"))
            )
            # Call unique() before extracting scalars
            cards = result.unique().scalars().all()

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

        if not card:
            await message.reply(
                "❌ **Erro:** Nenhum card encontrado com o ID ou nome fornecido.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Check if the user has the card in their inventory
        inventory_item = await session.execute(
            select(Inventory)
            .where(Inventory.user_id == message.from_user.id, Inventory.card_id == card.id)
        )
        inventory_item = inventory_item.scalar_one_or_none()

        if not inventory_item:
            await message.reply(
                "❌ **Erro:** Você não possui este card na sua mochila.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Fetch related details
        group = card.group
        category = group.category if group else None
        tags = {tag.name for tag in card.tags}  # Use a set to ensure uniqueness
        tags_str = f"🏷️ {', '.join(tags)}\n" if tags else ""

        # Prepare the response caption
        caption = (
            f"🎒Uau, @{message.from_user.username or 'usuário'}! encontrei na sua mochila o seguinte pokecard\n\n"
            f"🥇{card.id}. {card.name} ({inventory_item.quantity}x)\n"
            f"📚 {group.name if group else 'Nenhum'}\n"
            f"{tags_str}"
            "======================"
        )

        # Handle the card's image properly
        if card.image_file_id:
            try:
                # First, try sending as a photo
                await message.answer_photo(
                    photo=card.image_file_id,
                    caption=caption,
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                # If the error is due to a document being sent as a photo, send as document
                if "can't use file of type Document as Photo" in str(e):
                    await message.answer_document(
                        document=card.image_file_id,
                        caption=caption,
                        parse_mode=ParseMode.MARKDOWN
                    )
                else:
                    # Fallback to text for any other error
                    await message.reply(
                        caption,
                        parse_mode=ParseMode.MARKDOWN
                    )
        else:
            # Fallback to text if no image is available
            await message.reply(
                caption,
                parse_mode=ParseMode.MARKDOWN
            )