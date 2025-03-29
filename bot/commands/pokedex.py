from aiogram import Router, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from database.session import get_session
from database.models import User, Inventory, Card, Group, Category

router = Router()

# Emojis por raridade
RARITY_EMOJIS = {
    "🥇": "🥇",
    "🥈": "🥈",
    "🥉": "🥉"
}

def build_categories_keyboard(categories):
    buttons = [
        [InlineKeyboardButton(text=f"{cat.id}. {cat.name}", callback_data=f"pokedex_category:{cat.id}")]
        for cat in categories
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@router.message(Command(commands=["pokedex", "pd"]))
async def pokedex_command(message: types.Message):
    """
    Handles the /pokedex (or /pd) command.
    Shows a list of categories where the user owns at least one card.
    """
    user_id = message.from_user.id

    async with get_session() as session:
        result = await session.execute(
            select(Category)
            .join(Category.groups)
            .join(Group.cards)
            .join(Card.inventory)
            .where(Inventory.user_id == user_id)
            .options(selectinload(Category.groups))
        )
        categories = list({cat for cat in result.scalars().all()})

    if not categories:
        await message.reply("📭 Você ainda não possui cartas registradas na sua Pokédex.")
        return

    await message.answer(
        "📚 Escolha uma categoria para ver os cards registrados:",
        reply_markup=build_categories_keyboard(categories)
    )

@router.callback_query(lambda c: c.data.startswith("pokedex_category:"))
async def pokedex_category_callback(callback: CallbackQuery):
    """
    Callback handler for when a user selects a category from the /pokedex.
    Lists all cards of that category owned by the user.
    """
    category_id = int(callback.data.split(":"[1]))
    user_id = callback.from_user.id

    async with get_session() as session:
        result = await session.execute(
            select(Inventory)
            .join(Inventory.card)
            .join(Card.group)
            .join(Group.category)
            .where(Inventory.user_id == user_id, Category.id == category_id)
            .options(
                selectinload(Inventory.card).selectinload(Card.group).selectinload(Group.category),
                selectinload(Inventory.card)
            )
        )
        inventory_items = result.scalars().all()

    if not inventory_items:
        await callback.message.answer("📭 Você ainda não possui cards nesta categoria.")
        await callback.answer()
        return

    category_name = inventory_items[0].card.group.category.name

    sorted_cards = sorted(
        inventory_items,
        key=lambda i: (i.card.rarity, i.card.id)
    )

    total = sum(item.quantity for item in sorted_cards)
    unique = len(sorted_cards)

    card_lines = [
        f"{RARITY_EMOJIS.get(item.card.rarity, '')}{item.card.id}. {item.card.name} ({item.quantity}x)"
        for item in sorted_cards
    ]

    message_text = (
        f"🌼 Encontrei na Pokedex de {category_id}. {category_name} os seguintes cards:\n\n"
        + "\n".join(card_lines)
        + f"\n\nNo seu inventário há {total} de {unique} cards."
    )

    await callback.message.answer(message_text, parse_mode=ParseMode.MARKDOWN)
    await callback.answer()
