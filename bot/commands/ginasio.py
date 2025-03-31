from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from sqlalchemy import select, desc
from sqlalchemy.orm import joinedload
from database.session import get_session
from database.models import Card, Inventory, User

router = Router()

@router.message(Command("ginasio"))
async def ginasio_command(message: types.Message):
    """
    Handles the /ginasio <card_id> command.
    Shows the Top 10 users with most copies of the given card.
    """
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2 or not parts[1].isdigit():
        await message.reply(
            "❗ **Erro:** Use o comando com o ID de um card \n"
            "Exemplo: `/ginasio 20`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    card_id = int(parts[1])
    user_id = message.from_user.id

    async with get_session() as session:
        # Fetch the card with image and name
        card_result = await session.execute(
            select(Card).where(Card.id == card_id)
        )
        card = card_result.scalar_one_or_none()

        if not card:
            await message.reply(
                f"❌ **Erro:** Nenhum card encontrado com o ID `{card_id}`.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Get top 10 users with most of this card
        result = await session.execute(
            select(User.nickname, Inventory.quantity)
            .join(Inventory, Inventory.user_id == User.id)
            .where(Inventory.card_id == card_id)
            .order_by(desc(Inventory.quantity))
            .limit(10)
        )
        top_users = result.all()

        # Get the requesting user's position (if any)
        user_quantity_result = await session.execute(
            select(Inventory.quantity)
            .where(Inventory.user_id == user_id, Inventory.card_id == card_id)
        )
        user_quantity = user_quantity_result.scalar_one_or_none()

    # Build the ranking message
    title = f"Vejo que você não está entre os Top10 no ginásio de {card.id}. {card.name}:"
    if user_quantity:
        title = f"Você possui **{user_quantity}x** do card {card.id}. {card.name}, mas não está no Top 10:"

    medals = ["🥇", "🥈", "🥉"] + ["🏅"] * 7
    ranking_lines = []
    for i, (nickname, quantity) in enumerate(top_users):
        medal = medals[i] if i < len(medals) else "🏅"
        ranking_lines.append(f"{medal} {nickname} - {quantity}")

    caption = f"{title}\n\n" + "\n".join(ranking_lines)

    # Send the card image with the ranking
    if card.image_file_id:
        await message.answer_photo(
            photo=card.image_file_id,
            caption=caption,
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await message.reply(
            caption,
            parse_mode=ParseMode.MARKDOWN
        )
