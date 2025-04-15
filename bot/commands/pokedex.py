from aiogram import Router, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from database.session import get_session
from database.models import User, Group, Category, Inventory, Card

router = Router()

# Emojis por raridade
RARITY_EMOJIS = {
    "🥇": "🥇",
    "🥈": "🥈",
    "🥉": "🥉"
}

def build_categories_keyboard(categories: list[Category]) -> InlineKeyboardMarkup:
    buttons = []
    for cat in categories:
        btn_text = f"{cat.id}. {cat.name}"
        btn_data = f"pokedex_category:{cat.id}"
        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=btn_data)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def build_groups_keyboard(groups: list[Group]) -> InlineKeyboardMarkup:
    buttons = []
    for g in groups[:5]:  # limita a 5 grupos
        btn_text = f"{g.id}. {g.name}"
        btn_data = f"pokedex_group:{g.id}"
        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=btn_data)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def format_group_cards(cards: list[Card], user_inventory: dict[int, int], group_id: int, group_name: str, user_id: int) -> str:
    sorted_cards = sorted(cards, key=lambda c: (c.rarity, c.id))
    lines = []
    total_cards_user_owns = 0

    for card in sorted_cards:
        user_qty = user_inventory.get(card.id, 0)
        rarity_emoji = RARITY_EMOJIS.get(card.rarity, card.rarity)
        lines.append(f"{rarity_emoji}{card.id}. {card.name} ({user_qty}x)")
        total_cards_user_owns += user_qty

    total_cards_in_group = len(cards)

    return (
        f"🌼 Encontrei na Pokédex do grupo {group_id}. {group_name} os seguintes cards:\n\n"
        + "\n".join(lines)
        + f"\n\nNo seu inventário há {total_cards_user_owns} de {total_cards_in_group} cards deste grupo."
    )

HELP_MESSAGE = """
🎮 **Como usar o comando /pokedex**

📚 Ver todas as categorias:
• `/pokedex` (sem argumentos)

🔍 Buscar uma categoria específica:
• `/pokedex c ID` - busca por ID
• `/pokedex c Nome` - busca por nome

🎴 Buscar um grupo específico:
• `/pokedex g ID` - busca por ID
• `/pokedex g Nome` - busca por nome

Exemplo:
• `/pokedex c 1`
• `/pokedex g Pokemon`
"""

@router.message(Command(commands=["pokedex", "pd"]))
async def pokedex_command(message: Message) -> None:
    user_id = message.from_user.id
    parts = message.text.split(maxsplit=2)
    
    # Sem argumentos: mostrar categorias
    if len(parts) == 1:
        async with get_session() as session:
            categories_result = await session.execute(
                select(Category).options(selectinload(Category.groups))
            )
            categories = categories_result.scalars().all()

        if not categories:
            await message.answer("Nenhuma categoria disponível no momento.")
            return

        kb = build_categories_keyboard(categories)
        await message.answer("📚 Escolha uma categoria para ver seus grupos:", reply_markup=kb)
        return

    # Comando com argumentos incorretos
    if len(parts) != 3 or parts[1].lower() not in ['c', 'g']:
        await message.answer(HELP_MESSAGE, parse_mode=ParseMode.MARKDOWN)
        return

    type_arg = parts[1].lower()
    search_arg = parts[2]

    async with get_session() as session:
        if type_arg == 'c':  # Busca por categoria
            category = None
            if search_arg.isdigit():
                cat_id = int(search_arg)
                cat_result = await session.execute(select(Category).where(Category.id == cat_id))
                category = cat_result.scalar_one_or_none()
            else:
                cat_result = await session.execute(select(Category).where(Category.name.ilike(f"%{search_arg}%")))
                found = cat_result.scalars().all()
                if len(found) == 1:
                    category = found[0]
                elif len(found) > 1:
                    similar_cats = "\n".join(f"• ID {c.id}: {c.name}" for c in found)
                    await message.reply(
                        f"⚠️ **Múltiplas categorias encontradas com esse nome:**\n\n{similar_cats}\n\n"
                        "Use o ID para ser mais específico.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    return

            if not category:
                await message.reply(
                    "❌ **Categoria não encontrada**\nVerifique o ID ou nome e tente novamente.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

            # Buscar grupos da categoria
            group_result = await session.execute(
                select(Group)
                .join(Group.cards)
                .join(Card.inventory)
                .where(Group.category_id == category.id, Inventory.user_id == user_id)
                .options(selectinload(Group.category))
            )
            groups = list({g for g in group_result.scalars().all()})

            if not groups:
                await message.reply(
                    f"📝 **Categoria: {category.name}**\n\n"
                    "Você não possui nenhum card dessa categoria ainda.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

            kb = build_groups_keyboard(groups)
            await message.reply(
                f"📚 **Categoria: {category.name}**\n\n"
                "Escolha um grupo para ver suas cartas:",
                reply_markup=kb,
                parse_mode=ParseMode.MARKDOWN
            )

        else:  # type_arg == 'g', busca por grupo
            group = None
            if search_arg.isdigit():
                group_id = int(search_arg)
                group_result = await session.execute(select(Group).where(Group.id == group_id))
                group = group_result.scalar_one_or_none()
            else:
                group_result = await session.execute(select(Group).where(Group.name.ilike(f"%{search_arg}%")))
                found = group_result.scalars().all()
                if len(found) == 1:
                    group = found[0]
                elif len(found) > 1:
                    similar_groups = "\n".join(f"• ID {g.id}: {g.name}" for g in found)
                    await message.reply(
                        f"⚠️ **Múltiplos grupos encontrados com esse nome:**\n\n{similar_groups}\n\n"
                        "Use o ID para ser mais específico.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    return

            if not group:
                await message.reply(
                    "❌ **Grupo não encontrado**\nVerifique o ID ou nome e tente novamente.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

            # Restante do código existente para mostrar cards do grupo
            cards_result = await session.execute(select(Card).where(Card.group_id == group.id))
            cards_in_group = cards_result.scalars().all()

            inv_result = await session.execute(
                select(Inventory)
                .join(Inventory.card)
                .where(Inventory.user_id == user_id, Card.group_id == group.id)
            )
            user_inventory_list = inv_result.scalars().all()
            user_inventory_map = {inv.card_id: inv.quantity for inv in user_inventory_list}

            caption = format_group_cards(
                cards=cards_in_group,
                user_inventory=user_inventory_map,
                group_id=group.id,
                group_name=group.name,
                user_id=user_id
            )

            if group.image_file_id:
                await message.answer_photo(
                    photo=group.image_file_id,
                    caption=caption,
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await message.answer(caption, parse_mode=ParseMode.MARKDOWN)

@router.callback_query(lambda c: c.data.startswith("pokedex_category:"))
async def pokedex_category_callback(callback: CallbackQuery) -> None:
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

    async with get_session() as session:
        group_result = await session.execute(
            select(Group)
            .join(Group.cards)
            .join(Card.inventory)
            .where(Group.category_id == category_id, Inventory.user_id == user_id)
            .options(selectinload(Group.category))
        )
        groups = list({g for g in group_result.scalars().all()})

    if not groups:
        await callback.message.answer("Você não possui nenhum card dessa categoria.")
        await callback.answer()
        return

    kb = build_groups_keyboard(groups)
    await callback.message.answer("Escolha um grupo para ver suas cartas:", reply_markup=kb)
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("pokedex_group:"))
async def pokedex_group_callback(callback: CallbackQuery) -> None:
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
        group_result = await session.execute(select(Group).where(Group.id == group_id))
        group = group_result.scalar_one_or_none()

        if not group:
            await callback.message.answer("Esse grupo não existe ou foi removido.")
            await callback.answer()
            return

        cards_result = await session.execute(select(Card).where(Card.group_id == group_id))
        cards_in_group = cards_result.scalars().all()

        inv_result = await session.execute(
            select(Inventory)
            .join(Inventory.card)
            .where(Inventory.user_id == user_id, Card.group_id == group_id)
        )
        user_inventory_list = inv_result.scalars().all()
        user_inventory_map = {inv.card_id: inv.quantity for inv in user_inventory_list}

        caption = format_group_cards(
            cards=cards_in_group,
            user_inventory=user_inventory_map,
            group_id=group.id,
            group_name=group.name,
            user_id=user_id
        )

        if group.image_file_id:
            await callback.message.answer_photo(
                photo=group.image_file_id,
                caption=caption,
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await callback.message.answer(caption, parse_mode=ParseMode.MARKDOWN)

        await callback.answer()
