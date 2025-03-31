from aiogram import Router, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from sqlalchemy import select, update

from database.models import User, Inventory, Card
from database.session import get_session

router = Router()

# MODIFY THIS in models.py:
# class User(...):
#     ...
#     fav_card_id = Column(Integer, ForeignKey("cards.id"), nullable=True)
#     fav_emoji = Column(String(10), nullable=True)

@router.message(Command(commands=["favpoke"]))
async def favpoke_command(message: types.Message) -> None:
    """
    Sets the user's favorite card with an emoji.
    Usage: /favpoke <card_id> <emoji>
    """
    user_id = message.from_user.id
    args = message.text.split(maxsplit=2)

    if len(args) < 3:
        await message.reply(
            "❗ **Erro:** Uso incorreto do comando.\n"
            "Formato correto: `/favpoke <card_id> <emoji>`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    try:
        card_id = int(args[1])
        emoji = args[2].strip()
        if not emoji:
            raise ValueError
    except ValueError:
        await message.reply(
            "❗ **Erro:** Certifique-se de fornecer um ID de carta válido e um emoji.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    async with get_session() as session:
        # Verifica se o usuário existe
        user_result = await session.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            await message.reply("❌ Usuário não registrado.", parse_mode=ParseMode.MARKDOWN)
            return

        # Verifica se o card existe
        card_result = await session.execute(select(Card).where(Card.id == card_id))
        card = card_result.scalar_one_or_none()
        if not card:
            await message.reply("❌ Carta não encontrada.", parse_mode=ParseMode.MARKDOWN)
            return

        # Verifica se o usuário possui a carta no inventário
        inv_result = await session.execute(
            select(Inventory).where(Inventory.user_id == user_id, Inventory.card_id == card_id)
        )
        inv_item = inv_result.scalar_one_or_none()
        if not inv_item or inv_item.quantity <= 0:
            await message.reply(
                "❌ Você não possui essa carta no seu inventário.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Atualiza o favorito
        await session.execute(
            update(User)
            .where(User.id == user_id)
            .values(fav_card_id=card_id, fav_emoji=emoji)
        )
        await session.commit()

        caption = (
            f"⭐ Seu card favorito foi atualizado com sucesso!\n"
            f"{emoji} {card.rarity}{card.id}. {card.name}"
        )

        try:
            await message.answer_photo(
                photo=card.image_file_id,
                caption=caption,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception:
            await message.reply(caption, parse_mode=ParseMode.MARKDOWN)
