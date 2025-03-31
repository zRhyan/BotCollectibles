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

@router.message(Command(commands=["pokedex", "pd"]))
async def pokedex_command(message: Message) -> None:
    user_id = message.from_user.id
    parts = message.text.split(maxsplit=1)
    argument = parts[1].strip() if len(parts) > 1 else None

    # Caso não tenha argumento, mostrar categorias
    if not argument:
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

    # Caso tenha argumento: buscar grupo por ID ou nome
    async with get_session() as session:
        group = None
        if argument.isdigit():
            group_id = int(argument)
            group_result = await session.execute(select(Group).where(Group.id == group_id))
            group = group_result.scalar_one_or_none()
        else:
            group_result = await session.execute(select(Group).where(Group.name.ilike(f"%{argument}%")))
            found = group_result.scalars().all()
            if len(found) == 1:
                group = found[0]
            elif len(found) > 1:
                await message.reply(
                    "⚠️ **Erro:** Mais de um grupo encontrado com esse nome. Use o ID com `/pokedex ID`.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

        if not group:
            await message.reply("❌ Grupo não encontrado.", parse_mode=ParseMode.MARKDOWN)
            return

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
