from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from database.session import get_session
from database.models import Inventory, Card, Group, Category, User

router = Router()

# We'll use this callback data format for pagination
MOCHILA_CALLBACK = "mochila_page_{page}"

@router.message(Command("mochila"))
async def mochila_command(message: types.Message):
    """
    The /mochila command:
      1. Fetch the user's nickname and inventory from the database
      2. If empty, show a message that the mochila is empty
      3. Otherwise, paginate the results (10 items per page)
      4. Display the first page
    """
    user_id = message.from_user.id

    async with get_session() as session:
        # Get the user record to access user.nickname
        user_db = await session.get(User, user_id)
        if not user_db:
            await message.answer(
                "❌ Você ainda não se registrou.\nUse /jornada para iniciar.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Fetch user inventory (joined with Card->Group->Category)
        # Order by Card.id ASC (as requested)
        result = await session.execute(
            select(Inventory, Card, Group, Category)
            .join(Card, Inventory.card_id == Card.id)
            .join(Group, Card.group_id == Group.id)
            .join(Category, Group.category_id == Category.id)
            .where(Inventory.user_id == user_id)
            .order_by(Card.id.asc())
        )
        inventory = result.all()  # list of (Inventory, Card, Group, Category) tuples

        if not inventory:
            await message.answer(
                "🎒 **Sua Mochila está vazia!**\n"
                "Você ainda não capturou nenhum card...\n\n"
                "Use o comando /cap para lançar uma pokébola e tentar a sorte! 🍀",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Display the first page of items
        await send_mochila_page(message, inventory, page=1, nickname=user_db.nickname)

async def send_mochila_page(
    message_or_callback: types.Message | CallbackQuery,
    inventory: list,
    page: int,
    nickname: str
):
    """
    Sends (or edits) a paginated list of cards in the user’s mochila.
    10 items per page. The text format is:
      🎒Uau, @nickname! encontrei na sua mochila o seguinte pokecard

      🥇20. Karina (1x)
      📚 aespa

    page: current page number
    nickname: the user’s nickname from DB
    """
    items_per_page = 10
    start_index = (page - 1) * items_per_page
    end_index = start_index + items_per_page
    total_pages = (len(inventory) + items_per_page - 1) // items_per_page

    # Build the lines for this page
    # Each item is (Inventory, Card, Group, Category)
    page_items = inventory[start_index:end_index]

    lines = []
    for i, (inv, card, group, category) in enumerate(page_items, start=start_index + 1):
        # Rarity is assumed to be an emoji like 🥇 or 🥈 or 🥉
        # Example: 🥇20. Karina (1x)
        # Next line: 📚 aespa
        line = (
            f"{card.rarity}{card.id}. {card.name} ({inv.quantity}x)\n"  # first line
            f"📚 {category.name}"  # second line
        )
        lines.append(line)

    # Join all lines with a blank line between each or just a newline
    inventory_text = "\n\n".join(lines)

    text = (
        f"🎒Uau, @{nickname}! encontrei na sua mochila o seguinte pokecard\n\n"
        f"{inventory_text}\n\n"
        f"Página {page}/{total_pages}"
    )

    # Build pagination keyboard using InlineKeyboardBuilder
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

    keyboard.adjust(2)  # set 2 buttons per row

    # If the call is from a callback, use edit_text; else use answer()
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

@router.callback_query(lambda call: call.data.startswith("mochila_page_"))
async def mochila_pagination_callback(callback: CallbackQuery):
    """
    Handles pagination callbacks. Extracts the page from the callback data
    and re-fetches the user's inventory. Then calls send_mochila_page.
    """
    page = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id

    async with get_session() as session:
        # Get user & nickname
        user_db = await session.get(User, user_id)
        if not user_db:
            await callback.message.edit_text(
                "❌ Você ainda não se registrou.\nUse /jornada para iniciar.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Re-fetch inventory
        result = await session.execute(
            select(Inventory, Card, Group, Category)
            .join(Card, Inventory.card_id == Card.id)
            .join(Group, Card.group_id == Group.id)
            .join(Category, Group.category_id == Category.id)
            .where(Inventory.user_id == user_id)
            .order_by(Card.id.asc())
        )
        inventory = result.all()

    # Send the requested page
    await send_mochila_page(callback, inventory, page, nickname=user_db.nickname)
