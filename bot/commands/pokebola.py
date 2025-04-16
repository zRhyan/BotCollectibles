from aiogram import Router, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from sqlalchemy import select, update
from database.session import get_session
from database.models import Card, Group, Category, Tag, Inventory
from sqlalchemy.orm import joinedload
from bot.utils.image_utils import ensure_photo_file_id

router = Router()

def parse_pokebola_argument(text: str) -> str:
    """
    Parse the /pokebola command argument, handling quoted strings properly.
    Examples:
    '/pokebola 42' -> '42'
    '/pokebola "Pikachu"' -> 'Pikachu'
    """
    command_parts = text.split(maxsplit=1)
    if len(command_parts) < 2:
        return None
    
    arg = command_parts[1].strip()
    
    # Handle quoted search argument
    if arg.startswith('"') and arg.endswith('"'):
        # Remove surrounding quotes
        arg = arg[1:-1].strip()
    elif arg.startswith("'") and arg.endswith("'"):
        # Also handle single quotes
        arg = arg[1:-1].strip()
    
    return arg

@router.message(Command(commands=["pokebola", "pb"]))
async def pokebola_command(message: types.Message):
    """
    Handles the /pokebola (or /pb) command.
    Expects one argument: either card ID or exact card name (case-insensitive).
    For names with spaces, use quotes: /pokebola "Pikachu EX"
    Fetches the card, then sends its image and attributes.
    """
    # Parse arguments with better handling of quoted strings
    args = parse_pokebola_argument(message.text)
    if args is None:
        await message.reply(
            "❗ **Erro:** Forneça o ID ou nome exato do card. Exemplos:\n"
            "• `/pokebola 42` - busca pelo ID\n"
            "• `/pokebola \"Pikachu\"` - busca pelo nome exato (use aspas para nomes com espaços)",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    async with get_session() as session:
        # Query the card by ID or name with eager loading
        card = None
        if args.isdigit():
            # Search by ID (exact)
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
            # First try exact match (case-insensitive)
            result = await session.execute(
                select(Card)
                .options(
                    joinedload(Card.group).joinedload(Group.category),
                    joinedload(Card.tags)
                )
                .where(Card.name.ilike(args))  # Exact match, case-insensitive
            )
            cards_exact = result.unique().scalars().all()
            
            if len(cards_exact) == 1:
                card = cards_exact[0]
            elif len(cards_exact) > 1:
                # Multiple cards with exactly the same name (different case)
                # Just pick the first one since they're considered the same
                card = cards_exact[0]
            else:
                # If no exact match, try partial match to provide helpful suggestions
                result = await session.execute(
                    select(Card)
                    .options(
                        joinedload(Card.group).joinedload(Group.category),
                        joinedload(Card.tags)
                    )
                    .where(Card.name.ilike(f"%{args}%"))
                )
                similar_cards = result.unique().scalars().all()
                
                if similar_cards:
                    # Show suggestions if we found similar cards
                    similar_cards_list = "\n".join([f"• {c.id}. {c.name}" for c in similar_cards[:5]])
                    suggestion_text = f"Cards similares encontrados:\n{similar_cards_list}"
                    if len(similar_cards) > 5:
                        suggestion_text += f"\n...e {len(similar_cards) - 5} mais."
                    
                    await message.reply(
                        f"❌ **Erro:** Nenhum card com o nome exato '{args}' foi encontrado.\n\n"
                        f"{suggestion_text}\n\n"
                        "Por favor, use o ID exato do card ou escreva o nome completo.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                else:
                    await message.reply(
                        f"❌ **Erro:** Nenhum card encontrado com o nome '{args}'.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                return

        if not card:
            await message.reply(
                "❌ **Erro:** Nenhum card encontrado com o ID ou nome fornecido.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Remover verificação de inventário e modificar para mostrar quantidade se tiver
        inventory_item = await session.execute(
            select(Inventory)
            .where(Inventory.user_id == message.from_user.id, Inventory.card_id == card.id)
        )
        inventory_item = inventory_item.scalar_one_or_none()
        quantity_text = f" ({inventory_item.quantity}x)" if inventory_item else " (0x)"

        # Construção do caption formatado corretamente
        group = card.group
        category = group.name if group else "Nenhum"
        tags = [tag.name for tag in card.tags]
        has_tags = len(tags) > 0

        # Linha da tag, se existir
        tag_line = f"🏷️ {', '.join(tags)}\n" if has_tags else ""

        caption = (
            f"🎴 Card encontrado:\n\n"
            f"{card.rarity}{card.id}. {card.name}{quantity_text}\n"
            f"📚 {category}\n"
            f"{tag_line}"
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
                # If the error is due to a document being sent as a photo, convert it
                if "can't use file of type Document as Photo" in str(e):
                    try:
                        # Convert document to photo and get new file_id
                        new_photo_id = await ensure_photo_file_id(message.bot, types.Document(file_id=card.image_file_id))
                        
                        # Update the card in database with new photo file_id
                        await session.execute(
                            update(Card)
                            .where(Card.id == card.id)
                            .values(image_file_id=new_photo_id)
                        )
                        await session.commit()
                        
                        # Send the converted photo
                        await message.answer_photo(
                            photo=new_photo_id,
                            caption=caption,
                            parse_mode=ParseMode.MARKDOWN
                        )
                    except Exception as conv_error:
                        # Fallback to document if conversion fails
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