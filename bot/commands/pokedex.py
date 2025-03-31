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

def build_categories_keyboard(categories: list[Category]) -> InlineKeyboardMarkup:
    """
    Builds an inline keyboard of categories.
    """
    buttons = [
        [InlineKeyboardButton(text=f"{cat.id}. {cat.name}", callback_data=f"pokedex_category:{cat.id}")]
        for cat in categories
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def build_groups_keyboard(groups: list[Group]) -> InlineKeyboardMarkup:
    """
    Builds an inline keyboard of groups.
    """
    buttons = [
        [InlineKeyboardButton(text=f"{g.id}. {g.name}", callback_data=f"pokedex_group:{g.id}")]
        for g in groups
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def format_group_cards(inventory_items: list[Inventory], group_id: int, group_name: str) -> str:
    """
    Given a list of Inventory items for a specific group, returns the final text to be displayed.
    """
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
        f"🌼 Encontrei na sua Pokédex do grupo {group_id}. {group_name} os seguintes cards:\n\n"
        + "\n".join(card_lines)
        + f"\n\nNo seu inventário há {total} de {unique} cards desta coleção."
    )
    return message_text

@router.message(Command(commands=["pokedex", "pd"]))
async def pokedex_command(message: types.Message) -> None:
    """
    Handles the /pokedex (or /pd) command.
    1) If the user provides an argument (group ID or name), show that group's cards.
    2) Otherwise, lists all categories the user has, for further selection.
    """
    # Parse arguments
    text_parts = message.text.split(maxsplit=1)
    argument = text_parts[1].strip() if len(text_parts) > 1 else None
    user_id = message.from_user.id

    # Case 2: If no argument, show categories
    if not argument:
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
            "📚 Escolha uma categoria para ver os grupos registrados:",
            reply_markup=build_categories_keyboard(categories)
        )
        return

    # Case 1: The user provided an argument, so let's interpret it as a group ID or group name.
    async with get_session() as session:
        if argument.isdigit():
            group_id = int(argument)
            # Query for the group matching this ID
            group_result = await session.execute(
                select(Group)
                .where(Group.id == group_id)
            )
            group = group_result.scalar_one_or_none()
        else:
            # It's not a digit, interpret as group name
            group_result = await session.execute(
                select(Group)
                .where(Group.name.ilike(f"%{argument}%"))
            )
            groups_found = group_result.scalars().all()
            if len(groups_found) == 1:
                group = groups_found[0]
            elif len(groups_found) > 1:
                await message.reply(
                    "⚠️ **Erro:** Mais de um grupo encontrado com esse nome. Tente ser mais específico ou use o ID.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            else:
                group = None

        if not group:
            await message.reply(
                "❌ **Erro:** Nenhum grupo encontrado com o ID ou nome fornecido.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Now verify if user has cards from that group
        inv_result = await session.execute(
            select(Inventory)
            .join(Inventory.card)
            .where(Inventory.user_id == user_id, Card.group_id == group.id)
            .options(
                selectinload(Inventory.card).selectinload(Card.group),
                selectinload(Inventory.card)
            )
        )
        inventory_items = inv_result.scalars().all()

        if not inventory_items:
            await message.reply("📭 Você não possui nenhuma carta deste grupo.")
            return

        # Format the output
        text = format_group_cards(
            inventory_items=inventory_items,
            group_id=group.id,
            group_name=group.name
        )
        await message.reply(text, parse_mode=ParseMode.MARKDOWN)

@router.callback_query(lambda c: c.data.startswith("pokedex_category:"))
async def pokedex_category_callback(callback: CallbackQuery) -> None:
    """
    Callback handler for when a user selects a category.
    Lists all groups (within that category) that the user owns.
    """
    data_parts = callback.data.split(":")
    if len(data_parts) < 2:
        await callback.answer("Dados inválidos de categoria.", show_alert=True)
        return

    try:
        category_id = int(data_parts[1])
    except ValueError:
        await callback.answer("Dados inválidos de categoria.", show_alert=True)
        return

    user_id = callback.from_user.id

    # Retrieve groups for this category that the user has
    async with get_session() as session:
        group_result = await session.execute(
            select(Group)
            .join(Group.cards)
            .join(Card.inventory)
            .where(Inventory.user_id == user_id, Group.category_id == category_id)
            .options(selectinload(Group.category))
        )
        groups = list({g for g in group_result.scalars().all()})

    if not groups:
        await callback.message.answer("📭 Você não possui nenhum grupo nesta categoria.")
        await callback.answer()
        return

    await callback.message.answer(
        "Escolha um grupo para ver suas cartas:",
        reply_markup=build_groups_keyboard(groups)
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("pokedex_group:"))
async def pokedex_group_callback(callback: CallbackQuery) -> None:
    """
    Callback handler for when a user selects a group.
    Lists all cards in that group owned by the user.
    """
    data_parts = callback.data.split(":")
    if len(data_parts) < 2:
        await callback.answer("Dados inválidos de grupo.", show_alert=True)
        return

    try:
        group_id = int(data_parts[1])
    except ValueError:
        await callback.answer("Dados inválidos de grupo.", show_alert=True)
        return

    user_id = callback.from_user.id

    async with get_session() as session:
        inv_result = await session.execute(
            select(Inventory)
            .join(Inventory.card)
            .where(Inventory.user_id == user_id, Card.group_id == group_id)
            .options(
                selectinload(Inventory.card).selectinload(Card.group),
                selectinload(Inventory.card)
            )
        )
        inventory_items = inv_result.scalars().all()

        # Also fetch group to get its name
        group_result = await session.execute(
            select(Group).where(Group.id == group_id)
        )
        group = group_result.scalar_one_or_none()

    if not group:
        await callback.message.answer("Esse grupo não existe mais ou não é válido.")
        await callback.answer()
        return

    if not inventory_items:
        await callback.message.answer("📭 Você não possui nenhuma carta deste grupo.")
        await callback.answer()
        return

    # Format the output
    text = format_group_cards(
        inventory_items=inventory_items,
        group_id=group.id,
        group_name=group.name
    )
    await callback.message.answer(text, parse_mode=ParseMode.MARKDOWN)
    await callback.answer()
