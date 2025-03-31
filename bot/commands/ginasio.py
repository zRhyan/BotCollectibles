from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from sqlalchemy import select, desc
from sqlalchemy.orm import joinedload
from database.models import Card, Inventory, User
from database.session import get_session

router = Router()

@router.message(Command("ginasio"))
async def ginasio_command(message: types.Message):
    user_id = message.from_user.id
    parts = message.text.split(maxsplit=1)
    argument = parts[1].strip() if len(parts) > 1 else None

    if not argument or not argument.isdigit():
        await message.reply(
            "❗ **Erro:** Você deve fornecer o ID do card.\nExemplo: `/ginasio 20`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    card_id = int(argument)

    async with get_session() as session:
        # Busca o card
        card_result = await session.execute(
            select(Card).options(joinedload(Card.group)).where(Card.id == card_id)
        )
        card = card_result.scalar_one_or_none()

        if not card:
            await message.reply(
                "❌ **Erro:** Card não encontrado.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Ranking dos top 10 usuários com mais unidades do card
        inventory_result = await session.execute(
            select(Inventory, User)
            .join(User, Inventory.user_id == User.id)
            .where(Inventory.card_id == card_id)
            .order_by(desc(Inventory.quantity))
            .limit(10)
        )
        top_users = inventory_result.all()

    # Verifica se o usuário atual está no top 10
    user_in_top = any(user.id == user_id for inv, user in top_users)

    medals = ["🥇", "🥈", "🥉"] + ["🏅"] * 7
    rank_lines = []

    for idx, (inv, user) in enumerate(top_users):
        emoji = medals[idx] if idx < len(medals) else "🏅"
        rank_lines.append(f"{emoji} {user.nickname} - {inv.quantity}")

    if user_in_top:
        header = f"🏆 Você está entre os Top10 no ginásio de {card.id}. {card.name}:\n"
    else:
        header = f"👀 Vejo que você não está entre os Top10 no ginásio de {card.id}. {card.name}:\n"

    caption = header + "\n" + "\n".join(rank_lines)

    if card.image_file_id:
        try:
            await message.answer_photo(
                photo=card.image_file_id,
                caption=caption,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception:
            await message.reply(caption, parse_mode=ParseMode.MARKDOWN)
    else:
        await message.reply(caption, parse_mode=ParseMode.MARKDOWN)