from aiogram import Router, types, F
from aiogram.filters import Command, CommandObject
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message, InputMediaPhoto
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from database.session import get_session
from database.models import Inventory, Card, Group, Category, User

router = Router()

# Novo padrão para callback: mochila_page_{page}_user_{user_id}
MOCHILA_CALLBACK_PREFIX = "mochila_page"

@router.message(Command(commands=["mochila"], ignore_case=True, ignore_mention=True))
async def mochila_command(message: Message, command: CommandObject):
    args = (command.args or "").strip()

    async with get_session() as session:
        if args:
            username_lookup = args.lstrip("@").lower()
            stmt = select(User).where(
                (User.username.ilike(username_lookup)) |
                (User.nickname.ilike(f"%{username_lookup}%"))
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
            target_user = await session.get(User, message.from_user.id)
            if not target_user:
                await message.answer(
                    "❌ Você ainda não se registrou.\nUse /jornada para iniciar.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

        result = await session.execute(
            select(Inventory, Card, Group, Category)
            .join(Card, Inventory.card_id == Card.id)
            .join(Group, Card.group_id == Group.id)
            .join(Category, Group.category_id == Category.id)
            .where(Inventory.user_id == target_user.id, Inventory.quantity >= 1)
            .order_by(Card.id.asc())
        )
        inventory = result.all()

        # Separar a carta favorita
        fav_card = None
        if target_user.fav_card_id:
            fav_card_result = await session.execute(
                select(Card).where(Card.id == target_user.fav_card_id)
            )
            fav_card = fav_card_result.scalar_one_or_none()

    # Enviar a mensagem da carta favorita separadamente
    if fav_card and fav_card.image_file_id:
        fav_text = (
            f"{target_user.fav_emoji or ''} {fav_card.id}. {fav_card.name}\n"
            f"Raridade: {fav_card.rarity}\n\n"
            f"👤 @{target_user.nickname or target_user.username or 'Usuário'}"
        )
        await message.answer_photo(
            photo=fav_card.image_file_id,
            caption=fav_text,
            parse_mode=ParseMode.MARKDOWN
        )

    # Exibir inventário paginado
    if not inventory:
        await message.answer(
            f"🎒 **A mochila de @{target_user.username or target_user.nickname} está vazia!**\n"
            "Ainda não há cards registrados...\n\n"
            "Use o comando /cap para lançar uma pokébola e tentar a sorte! 🍀",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    await send_mochila_page(
        message,
        inventory,
        page=1,
        user_id=target_user.id,
        nickname=target_user.nickname or target_user.username or "Usuário"
    )


async def send_mochila_page(
    message_or_callback: Message | CallbackQuery,
    inventory: list,
    page: int,
    user_id: int,
    nickname: str
):
    items_per_page = 10
    start_index = (page - 1) * items_per_page
    end_index = start_index + items_per_page
    total_pages = (len(inventory) + items_per_page - 1) // items_per_page
    page_items = inventory[start_index:end_index]

    lines = []
    for i, (inv, card, group, category) in enumerate(page_items, start=start_index + 1):
        line = f"{card.rarity}{card.id}. {card.name} ({inv.quantity}x)"
        lines.append(line)

    inventory_text = "\n".join(lines)
    header = f"🎒 Uau, @{nickname}! Aqui está sua mochila:\n\n"
    text = f"{header}{inventory_text}\n\nPágina {page}/{total_pages}"

    keyboard = InlineKeyboardBuilder()
    if page > 1:
        keyboard.button(
            text="⬅️ Anterior",
            callback_data=f"{MOCHILA_CALLBACK_PREFIX}_{page - 1}_user_{user_id}"
        )
    if page < total_pages:
        keyboard.button(
            text="Próximo ➡️",
            callback_data=f"{MOCHILA_CALLBACK_PREFIX}_{page + 1}_user_{user_id}"
        )
    keyboard.adjust(2)

    if isinstance(message_or_callback, CallbackQuery):
        await message_or_callback.message.edit_text(
            text,
            reply_markup=keyboard.as_markup(),
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await message_or_callback.answer(
            text,
            reply_markup=keyboard.as_markup(),
            parse_mode=ParseMode.MARKDOWN
        )


@router.callback_query(F.data.startswith("mochila_page_"))
async def mochila_pagination_callback(callback: CallbackQuery):
    """
    Exibe a página da mochila do usuário original (não de quem clicou).
    """
    try:
        # Extrai página e user_id do callback_data
        parts = callback.data.split("_")
        page = int(parts[2])
        user_id = int(parts[4])
    except Exception:
        await callback.answer("❌ Erro ao processar a navegação da mochila.", show_alert=True)
        return

    async with get_session() as session:
        user = await session.get(User, user_id)
        if not user:
            await callback.answer("❌ Usuário original não encontrado.", show_alert=True)
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
        user_id=user.id,
        nickname=user.nickname or user.username or "Usuário"
    )
