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

CARDS_PER_PAGE = 30

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

def format_group_cards(
    cards: list[Card], 
    user_inventory: dict[int, int], 
    group_id: int, 
    group_name: str, 
    user_id: int,
    page: int = 1
) -> tuple[str, int]:
    """Returns (formatted_text, total_pages)"""
    sorted_cards = sorted(cards, key=lambda c: (c.rarity, c.id))
    total_pages = (len(sorted_cards) + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE
    
    start_idx = (page - 1) * CARDS_PER_PAGE
    end_idx = start_idx + CARDS_PER_PAGE
    page_cards = sorted_cards[start_idx:end_idx]
    
    lines = []
    total_cards_user_owns = sum(user_inventory.get(card.id, 0) for card in cards)
    
    for card in page_cards:
        user_qty = user_inventory.get(card.id, 0)
        rarity_emoji = RARITY_EMOJIS.get(card.rarity, card.rarity)
        lines.append(f"{rarity_emoji}{card.id}. {card.name} ({user_qty}x)")

    return (
        f"🌼 Pokédex do grupo {group_id}. {group_name}"
        f"\nPágina {page}/{total_pages}\n\n"
        f"{chr(10).join(lines)}\n\n"
        f"No seu inventário há {total_cards_user_owns} de {len(cards)} cards deste grupo."
    ), total_pages

def build_group_navigation_keyboard(group_id: int, current_page: int, total_pages: int) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    
    if current_page > 1:
        row.append(InlineKeyboardButton(
            text="⬅️ Anterior",
            callback_data=f"pokedex_group_page:{group_id}:{current_page-1}"
        ))
    
    if current_page < total_pages:
        row.append(InlineKeyboardButton(
            text="Próximo ➡️",
            callback_data=f"pokedex_group_page:{group_id}:{current_page+1}"
        ))
    
    if row:
        buttons.append(row)
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

HELP_MESSAGE = """
🎮 **Como usar o comando /pokedex**

📚 Ver todas as categorias:
• `/pokedex` (sem argumentos)

🔍 Buscar uma categoria específica:
• `/pokedex c ID` - busca por ID
• `/pokedex c "Nome da Categoria"` - busca pelo nome exato (use aspas para nomes com espaços)

🎴 Buscar um grupo específico:
• `/pokedex g ID` - busca por ID
• `/pokedex g "Nome do Grupo"` - busca pelo nome exato (use aspas para nomes com espaços)

Exemplo:
• `/pokedex c 1`
• `/pokedex g "Pokemon Red"`
• `/pokedex c "K-Pop Idols"`
"""

def parse_command_arguments(text: str) -> tuple[str, str]:
    """
    Parse command arguments handling quoted strings properly.
    Returns a tuple of (type_arg, search_arg)
    
    Examples:
    '/pokedex c 1' -> ('c', '1')
    '/pokedex g "BTS DISCO"' -> ('g', 'BTS DISCO')
    """
    command_parts = text.split(maxsplit=1)
    if len(command_parts) < 2:
        return None, None
    
    args_text = command_parts[1].strip()
    
    # Split by first space to get type_arg
    if ' ' not in args_text:
        return args_text.lower(), None
    
    type_arg, remaining = args_text.split(maxsplit=1)
    type_arg = type_arg.lower()
    
    # Handle quoted search argument
    search_arg = remaining.strip()
    if search_arg.startswith('"') and search_arg.endswith('"'):
        # Remove surrounding quotes
        search_arg = search_arg[1:-1].strip()
    elif search_arg.startswith("'") and search_arg.endswith("'"):
        # Also handle single quotes
        search_arg = search_arg[1:-1].strip()
    
    return type_arg, search_arg

@router.message(Command(commands=["pokedex", "pd"]))
async def pokedex_command(message: Message) -> None:
    user_id = message.from_user.id
    
    # Parse arguments with better handling of quoted strings
    type_arg, search_arg = parse_command_arguments(message.text)
    
    # Sem argumentos: mostrar categorias
    if type_arg is None:
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
    if type_arg not in ['c', 'g'] or search_arg is None:
        await message.answer(HELP_MESSAGE, parse_mode=ParseMode.MARKDOWN)
        return

    async with get_session() as session:
        if type_arg == 'c':  # Busca por categoria
            category = None
            if search_arg.isdigit():
                # Search by ID (exact)
                cat_id = int(search_arg)
                cat_result = await session.execute(select(Category).where(Category.id == cat_id))
                category = cat_result.scalar_one_or_none()
            else:
                # Try exact match (case-insensitive) using func.lower
                from sqlalchemy import func
                search_lower = search_arg.lower()
                cat_result = await session.execute(
                    select(Category).where(func.lower(Category.name) == search_lower)
                )
                exact_categories = cat_result.scalars().all()
                
                if len(exact_categories) == 1:
                    category = exact_categories[0]
                elif len(exact_categories) > 1:
                    # No improvável caso de categorias com mesmo nome
                    category = exact_categories[0]
                else:
                    # Se não encontrar correspondência exata, procura similares
                    cat_result = await session.execute(
                        select(Category).where(func.lower(Category.name).like(f"%{search_lower}%"))
                    )
                    similar_categories = cat_result.scalars().all()
                    
                    if similar_categories:
                        # Organiza os resultados similares por comprimento do nome
                        similar_categories.sort(key=lambda x: abs(len(x.name) - len(search_arg)))
                        similar_cats = "\n".join(f'• ID {c.id}: "{c.name}"' for c in similar_categories[:5])
                        await message.reply(
                            f'❌ **Categoria não encontrada**\n\n'
                            f'Não encontrei uma categoria com exatamente o nome "{search_arg}".\n\n'
                            f'Você quis dizer:\n{similar_cats}\n\n'
                            'Use aspas para nomes compostos. Exemplo: `/pokedex c "Nome Composto"`\n'
                            'Ou use o ID para ser mais específico.',
                            parse_mode=ParseMode.MARKDOWN
                        )
                    else:
                        await message.reply(
                            f'❌ **Categoria não encontrada**\nNenhuma categoria com o nome "{search_arg}" foi encontrada.',
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
                # Search by ID (exact)
                group_id = int(search_arg)
                group_result = await session.execute(select(Group).where(Group.id == group_id))
                group = group_result.scalar_one_or_none()
            else:
                # Try exact match (case-insensitive) using func.lower for exact comparison
                from sqlalchemy import func
                search_lower = search_arg.lower()
                group_result = await session.execute(
                    select(Group).where(func.lower(Group.name) == search_lower)
                )
                exact_groups = group_result.scalars().all()
                
                if len(exact_groups) == 1:
                    group = exact_groups[0]
                elif len(exact_groups) > 1:
                    # No conflito improvável de grupos com mesmo nome
                    group = exact_groups[0]
                else:
                    # Se não encontrar correspondência exata, procura similares
                    group_result = await session.execute(
                        select(Group).where(func.lower(Group.name).like(f"%{search_lower}%"))
                    )
                    similar_groups = group_result.scalars().all()
                    
                    if similar_groups:
                        # Organiza os resultados similares por comprimento do nome (mais próximo primeiro)
                        similar_groups.sort(key=lambda x: abs(len(x.name) - len(search_arg)))
                        similar_groups_list = "\n".join(f'• ID {g.id}: "{g.name}"' for g in similar_groups[:5])
                        await message.reply(
                            f'❌ **Grupo não encontrado**\n\n'
                            f'Não encontrei um grupo com exatamente o nome "{search_arg}".\n\n'
                            f'Você quis dizer:\n{similar_groups_list}\n\n'
                            'Use aspas para nomes compostos. Exemplo: `/pokedex g "Nome Composto"`\n'
                            'Ou use o ID para ser mais específico.',
                            parse_mode=ParseMode.MARKDOWN
                        )
                    else:
                        await message.reply(
                            f'❌ **Grupo não encontrado**\nNenhum grupo com o nome "{search_arg}" foi encontrado.',
                            parse_mode=ParseMode.MARKDOWN
                        )
                    return

            await show_group_cards(message, group.id, user_id)

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

    await show_group_cards(callback, group_id, user_id)

async def show_group_cards(message_or_callback: Message | CallbackQuery, group_id: int, user_id: int, page: int = 1) -> None:
    async with get_session() as session:
        group_result = await session.execute(select(Group).where(Group.id == group_id))
        group = group_result.scalar_one_or_none()

        if not group:
            msg = "Esse grupo não existe ou foi removido."
            if isinstance(message_or_callback, CallbackQuery):
                await message_or_callback.message.answer(msg)
                await message_or_callback.answer()
            else:
                await message_or_callback.answer(msg)
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

        caption, total_pages = format_group_cards(
            cards=cards_in_group,
            user_inventory=user_inventory_map,
            group_id=group.id,
            group_name=group.name,
            user_id=user_id,
            page=page
        )

        keyboard = build_group_navigation_keyboard(group.id, page, total_pages)

        if group.image_file_id:
            if isinstance(message_or_callback, CallbackQuery):
                try:
                    await message_or_callback.message.edit_caption(
                        caption=caption,
                        reply_markup=keyboard,
                        parse_mode=ParseMode.MARKDOWN
                    )
                except Exception:
                    # Se não conseguir editar, envia nova mensagem
                    await message_or_callback.message.answer_photo(
                        photo=group.image_file_id,
                        caption=caption,
                        reply_markup=keyboard,
                        parse_mode=ParseMode.MARKDOWN
                    )
            else:
                await message_or_callback.answer_photo(
                    photo=group.image_file_id,
                    caption=caption,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.MARKDOWN
                )
        else:
            if isinstance(message_or_callback, CallbackQuery):
                await message_or_callback.message.edit_text(
                    text=caption,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await message_or_callback.answer(
                    text=caption,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.MARKDOWN
                )

@router.callback_query(lambda c: c.data.startswith("pokedex_group_page:"))
async def handle_group_pagination(callback: CallbackQuery) -> None:
    try:
        _, group_id, page = callback.data.split(":")
        group_id = int(group_id)
        page = int(page)
    except (ValueError, IndexError):
        await callback.answer("Dados inválidos.", show_alert=True)
        return

    await show_group_cards(callback, group_id, callback.from_user.id, page)
    await callback.answer()
