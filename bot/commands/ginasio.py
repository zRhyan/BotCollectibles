from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from sqlalchemy import select, desc
from sqlalchemy.orm import joinedload

from database.models import Card, Inventory, User
from database.session import get_session

router = Router()

@router.message(Command("ginasio"))
async def ginasio_command(message: types.Message) -> None:
    """
    Handles the /ginasio <card_id> command.
    Shows the Top 10 users who have the highest quantity of the specified card.
    
    Example usage:
        /ginasio 20
    """
    user_id = message.from_user.id

    # Extract the argument (card_id)
    parts = message.text.split(maxsplit=1)
    argument = parts[1].strip() if len(parts) > 1 else None

    # Check if card_id is provided and valid
    if not argument or not argument.isdigit():
        await message.reply(
            "❗ **Erro:** Você deve fornecer o ID do card.\n"
            "Exemplo: `/ginasio 20`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    card_id = int(argument)

    async with get_session() as session:
        # Fetch the card (with optional group info)
        card_query = (
            select(Card)
            .options(joinedload(Card.group))  # only needed if you want group info
            .where(Card.id == card_id)
        )
        card_result = await session.execute(card_query)
        card = card_result.scalar_one_or_none()

        if not card:
            await message.reply(
                f"❌ **Erro:** Nenhum card encontrado com o ID `{card_id}`.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Get top 10 users who hold the most copies of this card
        inv_query = (
            select(Inventory, User)
            .join(User, Inventory.user_id == User.id)
            .where(Inventory.card_id == card_id)
            .order_by(desc(Inventory.quantity))
            .limit(10)
        )
        inventory_result = await session.execute(inv_query)
        top_users = inventory_result.all()  # List[(Inventory, User)]

    # Check if the current user is in top 10
    user_in_top = any(u.id == user_id for _, u in top_users)

    # Prepare ranking lines (medals for top positions)
    medals = ["🥇", "🥈", "🥉"] + ["🏅"] * 7
    rank_lines = []
    for idx, (inv_item, user_db) in enumerate(top_users):
        medal = medals[idx] if idx < len(medals) else "🏅"
        rank_lines.append(f"{medal} {user_db.nickname} - {inv_item.quantity}")

    # Construct header message
    if user_in_top:
        header = (
            f"🏆 Você está entre os Top 10 do ginásio de {card.id}. {card.name}:\n"
        )
    else:
        header = (
            f"👀 Vejo que você não está entre os Top 10 no ginásio de {card.id}. {card.name}:\n"
        )

    # Combine header + ranking lines
    caption = header + "\n" + "\n".join(rank_lines)

    # If there's an image, send as a photo; else fallback to text
    if card.image_file_id:
        try:
            await message.answer_photo(
                photo=card.image_file_id,
                caption=caption,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            # If something goes wrong sending as photo, fallback to text
            await message.reply(
                caption,
                parse_mode=ParseMode.MARKDOWN
            )
    else:
        await message.reply(
            caption,
            parse_mode=ParseMode.MARKDOWN
        )
