from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from database.session import get_session
from database.models import Inventory, Card, Group, Category, User

router = Router()

# Callback data para paginação
MOCHILA_CALLBACK = "mochila_page_{page}"

@router.message(Command("mochila"))
async def mochila_command(message: types.Message):
    """
    Exibe a mochila (inventário) de cartas de um usuário.
    Se for passado um argumento (username ou nickname), consulta a mochila de outro usuário.
    Caso nenhum argumento seja passado, exibe a mochila do próprio usuário.
    Apenas cartas com quantidade >= 1 são retornadas.
    """
    # Verifica se foi passado argumento para consulta de outra mochila
    args = message.get_args().strip()
    if args:
        # Remove o "@" se presente e converte para minúsculas para comparação
        target_str = args.lstrip("@").lower()
        async with get_session() as session:
            # Tenta buscar o usuário pelo username (exato) ou pelo nickname (case-insensitive)
            stmt = select(User).where(
                (User.username.ilike(target_str)) |
                (User.nickname.ilike(f"%{target_str}%"))
            )
            result = await session.execute(stmt)
            target_user = result.scalar_one_or_none()
            if not target_user:
                await message.answer(
                    f"❌ Usuário '{args}' não encontrado.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
    else:
        # Se não foi passado argumento, o usuário alvo é o próprio usuário que enviou o comando
        async with get_session() as session:
            target_user = await session.get(User, message.from_user.id)
            if not target_user:
                await message.answer(
                    "❌ Você ainda não se registrou.\nUse /jornada para iniciar.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

    target_id = target_user.id

    # Busca o inventário filtrando apenas cartas com quantidade >= 1
    async with get_session() as session:
        result = await session.execute(
            select(Inventory, Card, Group, Category)
            .join(Card, Inventory.card_id == Card.id)
            .join(Group, Card.group_id == Group.id)
            .join(Category, Group.category_id == Category.id)
            .where(Inventory.user_id == target_id, Inventory.quantity >= 1)
            .order_by(Card.id.asc())
        )
        inventory = result.all()

    if not inventory:
        await message.answer(
            f"🎒 **A mochila de @{target_user.username or target_user.nickname} está vazia!**\n"
            "Você ainda não capturou nenhum card...\n\n"
            "Use o comando /cap para lançar uma pokébola e tentar a sorte! 🍀",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    await send_mochila_page(
        message,
        inventory,
        page=1,
        nickname=target_user.nickname or target_user.username or "Usuário",
        fav_card_id=target_user.fav_card_id,
        fav_emoji=target_user.fav_emoji
    )


async def send_mochila_page(
    message_or_callback: types.Message | CallbackQuery,
    inventory: list,
    page: int,
    nickname: str,
    fav_card_id: int | None = None,
    fav_emoji: str | None = None
):
    """
    Monta a página da mochila para exibição, com paginação.
    """
    items_per_page = 10
    start_index = (page - 1) * items_per_page
    end_index = start_index + items_per_page
    total_pages = (len(inventory) + items_per_page - 1) // items_per_page

    page_items = inventory[start_index:end_index]

    lines = []
    fav_card = None
    for i, (inv, card, group, category) in enumerate(page_items, start=start_index + 1):
        line = f"{card.rarity}{card.id}. {card.name} ({inv.quantity}x)"
        lines.append(line)
        if fav_card_id and card.id == fav_card_id:
            fav_card = card

    inventory_text = "\n".join(lines)
    
    header = f"🎒 Uau, @{nickname}! Aqui está sua mochila:\n\n"

    if fav_card_id and fav_emoji and fav_card:
        header = f"{fav_emoji} {fav_card.id}. {fav_card.name}\n\n" + header

    text = header + inventory_text + f"\n\nPágina {page}/{total_pages}"

    keyboard = InlineKeyboardBuilder()

    if page > 1:
        keyboard.button(
            text="⬅️ Anterior",
            callback_data=MOCHILA_CALLBACK.format(page=page - 1)
        )

    if page < total_pages:
        keyboard.button(
            text="Próximo ➡️",
            callback_data=MOCHILA_CALLBACK.format(page=page + 1)
        )

    keyboard.adjust(2)

    if isinstance(message_or_callback, CallbackQuery):
        if fav_card and fav_card.image_file_id:
            await message_or_callback.message.edit_media(
                media=types.InputMediaPhoto(
                    media=fav_card.image_file_id,
                    caption=text,
                    parse_mode=ParseMode.MARKDOWN
                ),
                reply_markup=keyboard.as_markup()
            )
        else:
            await message_or_callback.message.edit_text(
                text,
                reply_markup=keyboard.as_markup(),
                parse_mode=ParseMode.MARKDOWN
            )
    else:
        if fav_card and fav_card.image_file_id:
            await message_or_callback.answer_photo(
                photo=fav_card.image_file_id,
                caption=text,
                reply_markup=keyboard.as_markup(),
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await message_or_callback.answer(
                text,
                reply_markup=keyboard.as_markup(),
                parse_mode=ParseMode.MARKDOWN
            )


@router.callback_query(lambda call: call.data.startswith("mochila_page_"))
async def mochila_pagination_callback(callback: CallbackQuery):
    """
    Handler para paginação da mochila.
    Reexecuta a query para atualizar o inventário com o filtro de quantidade >= 1.
    """
    page = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id

    async with get_session() as session:
        user_db = await session.get(User, user_id)
        if not user_db:
            await callback.message.edit_text(
                "❌ Você ainda não se registrou.\nUse /jornada para iniciar.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        result = await session.execute(
            select(Inventory, Card, Group, Category)
            .join(Card, Inventory.card_id == Card.id)
            .join(Group, Card.group_id == Group.id)
            .join(Category, Group.category_id == Category.id)
            .where(Inventory.user_id == user_id, Inventory.quantity >= 1)
            .order_by(Card.id.asc())
        )
        inventory = result.all()

    await send_mochila_page(
        callback,
        inventory,
        page,
        nickname=user_db.nickname or user_db.username or "Usuário",
        fav_card_id=user_db.fav_card_id,
        fav_emoji=user_db.fav_emoji
    )
