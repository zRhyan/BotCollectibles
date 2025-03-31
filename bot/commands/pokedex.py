from aiogram import Router, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from sqlalchemy import select
from sqlalchemy.orm import selectinload, joinedload

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
    Builds an inline keyboard of ALL categories.
    """
    buttons = []
    for cat in categories:
        btn_text = f"{cat.id}. {cat.name}"
        btn_data = f"pokedex_category:{cat.id}"
        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=btn_data)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def build_groups_keyboard(groups: list[Group]) -> InlineKeyboardMarkup:
    """
    Builds an inline keyboard of groups within a category.
    """
    buttons = []
    for g in groups:
        btn_text = f"{g.id}. {g.name}"
        btn_data = f"pokedex_group:{g.id}"
        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=btn_data)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def format_group_cards(
    cards: list[Card],
    user_inventory: dict[int, int],
    group_id: int,
    group_name: str,
    user_id: int
) -> str:
    """
    Dado uma lista de cards do grupo (TODOS do BD) e um dicionário mapeando card_id -> quantidade para o usuário,
    retornamos o texto final.

    :param cards: lista de todos os Card pertencentes ao grupo.
    :param user_inventory: dicionário {card_id: quantity} de posse do usuário.
    :param group_id: id do grupo.
    :param group_name: nome do grupo.
    :param user_id: id do usuário (para citar ou personalizar se quiser).
    :return: string final formatada.
    """
    # Organiza os cards por raridade e ID
    sorted_cards = sorted(cards, key=lambda c: (c.rarity, c.id))

    # Monta cada linha com a quantidade do usuário (ou 0)
    lines = []
    total_cards_user_owns = 0

    for card in sorted_cards:
        user_qty = user_inventory.get(card.id, 0)
        if card.rarity in RARITY_EMOJIS:
            rarity_emoji = RARITY_EMOJIS[card.rarity]
        else:
            rarity_emoji = card.rarity  # fallback
        line = f"{rarity_emoji}{card.id}. {card.name} ({user_qty}x)"
        lines.append(line)
        total_cards_user_owns += user_qty

    total_cards_in_group = len(cards)

    # Monta a mensagem final
    msg = (
        f"🌼 Encontrei na Pokédex do grupo {group_id}. {group_name} os seguintes cards:\n\n"
        + "\n".join(lines)
        + f"\n\nNo seu inventário há {total_cards_user_owns} de {total_cards_in_group} cards deste grupo."
    )

    return msg

@router.message(Command(commands=["pokedex", "pd"]))
async def pokedex_command(message: types.Message) -> None:
    """
    Comando /pokedex (ou /pd).

    1) Se o usuário não informar nada além de /pokedex, listamos TODAS as categorias do BD.
    2) Se o usuário informar algo (nome ou ID do grupo), procuramos esse grupo, listamos todos os cards do grupo,
       mas no final mostramos quantos cards o usuário possui dele.
    """
    # Verifica se temos um argumento após o comando
    parts = message.text.split(maxsplit=1)
    argument = parts[1].strip() if len(parts) > 1 else None
    user_id = message.from_user.id

    # Caso 1: Sem argumento => mostrar todas as categorias
    if not argument:
        async with get_session() as session:
            # Pega TODAS as categorias do banco, independente do user
            categories_result = await session.execute(
                select(Category)
                .options(selectinload(Category.groups))
            )
            categories = categories_result.scalars().all()

        if not categories:
            await message.reply("Não há categorias cadastradas no momento.")
            return

        kb = build_categories_keyboard(categories)
        await message.answer(
            "📚 Escolha uma categoria para ver seus grupos:",
            reply_markup=kb
        )
        return

    # Caso 2: Temos argumento => é ID ou nome do grupo
    async with get_session() as session:
        group = None
        if argument.isdigit():
            g_id = int(argument)
            group_result = await session.execute(
                select(Group).where(Group.id == g_id)
            )
            group = group_result.scalar_one_or_none()
        else:
            group_result = await session.execute(
                select(Group).where(Group.name.ilike(f"%{argument}%"))
            )
            found = group_result.scalars().all()
            if len(found) == 1:
                group = found[0]
            elif len(found) > 1:
                await message.reply(
                    "⚠️ **Erro:** Mais de um grupo encontrado com esse nome. Tente ser mais específico ou use o ID.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

        if not group:
            await message.reply(
                "❌ **Erro:** Nenhum grupo encontrado com o ID ou nome fornecido.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Pega TODOS os cards do grupo
        cards_result = await session.execute(
            select(Card)
            .options(selectinload(Card.group))
            .where(Card.group_id == group.id)
        )
        cards_in_group = cards_result.scalars().all()

        if not cards_in_group:
            await message.reply(
                "Não há cards cadastrados nesse grupo.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Pega quantos cards desse grupo o usuário possui => dicionário card_id -> quantity
        inv_result = await session.execute(
            select(Inventory)
            .join(Inventory.card)
            .where(Inventory.user_id == user_id, Card.group_id == group.id)
        )
        user_inventory_list = inv_result.scalars().all()
        user_inventory_map = {inv.card_id: inv.quantity for inv in user_inventory_list}

        final_text = format_group_cards(
            cards=cards_in_group,
            user_inventory=user_inventory_map,
            group_id=group.id,
            group_name=group.name,
            user_id=user_id
        )
        await message.reply(final_text, parse_mode=ParseMode.MARKDOWN)

@router.callback_query(lambda c: c.data.startswith("pokedex_category:"))
async def pokedex_category_callback(callback: CallbackQuery) -> None:
    """
    Quando o usuário escolhe uma categoria, listamos TODOS os grupos dessa categoria.
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

    async with get_session() as session:
        # Pega TODOS os grupos da categoria, independente do user
        groups_result = await session.execute(
            select(Group)
            .where(Group.category_id == category_id)
        )
        groups = groups_result.scalars().all()

    if not groups:
        await callback.message.answer("Não há grupos cadastrados nessa categoria.")
        await callback.answer()
        return

    kb = build_groups_keyboard(groups)
    await callback.message.answer(
        "Escolha um grupo para ver suas cartas:",
        reply_markup=kb
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("pokedex_group:"))
async def pokedex_group_callback(callback: CallbackQuery) -> None:
    """
    Quando o usuário seleciona um grupo, listamos TODOS os cards do grupo,
    mas informamos quantos o usuário possui.
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
        group_result = await session.execute(
            select(Group).where(Group.id == group_id)
        )
        group = group_result.scalar_one_or_none()

        if not group:
            await callback.message.answer("Esse grupo não existe ou foi removido.")
            await callback.answer()
            return

        # Pega todos os cards do grupo
        cards_result = await session.execute(
            select(Card)
            .where(Card.group_id == group_id)
        )
        cards_in_group = cards_result.scalars().all()

        if not cards_in_group:
            await callback.message.answer("Não há cards cadastrados nesse grupo.")
            await callback.answer()
            return

        # Mapeia o inventário do usuário => card_id -> quantity
        inv_result = await session.execute(
            select(Inventory)
            .join(Inventory.card)
            .where(Inventory.user_id == user_id, Card.group_id == group_id)
        )
        user_inventory_list = inv_result.scalars().all()
        user_inventory_map = {inv.card_id: inv.quantity for inv in user_inventory_list}

        final_text = format_group_cards(
            cards=cards_in_group,
            user_inventory=user_inventory_map,
            group_id=group.id,
            group_name=group.name,
            user_id=user_id
        )
        await callback.message.answer(final_text, parse_mode=ParseMode.MARKDOWN)

    await callback.answer()
