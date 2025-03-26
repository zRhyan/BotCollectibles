from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from sqlalchemy.future import select
from database.session import get_session
from database.models import Inventory, Card, Group, Category
from aiogram.enums import ParseMode

router = Router()

# Callback data for pagination
MOCHILA_CALLBACK = "mochila_page_{page}"


@router.message(Command("mochila"))
async def mochila_command(message: types.Message):
    user_id = message.from_user.id

    async with get_session() as session:
        # Fetch user inventory
        result = await session.execute(
            select(Inventory, Card, Group, Category)
            .join(Card, Inventory.card_id == Card.id)
            .join(Group, Card.group_id == Group.id)
            .join(Category, Group.category_id == Category.id)
            .where(Inventory.user_id == user_id)
            .order_by(Card.rarity.desc(), Card.name.asc())
        )
        inventory = result.all()

        if not inventory:
            await message.answer(
                "🎒 **Sua Mochila está vazia!**\n"
                "Você ainda não capturou nenhum card...\n\n"
                "Use o comando /cap para lançar uma pokébola e tentar a sorte! 🍀",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Paginate and display the first page
        await send_mochila_page(message, inventory, page=1)


async def send_mochila_page(message: types.Message, inventory, page: int):
    # Pagination settings
    items_per_page = 10
    start_index = (page - 1) * items_per_page
    end_index = start_index + items_per_page
    total_pages = (len(inventory) + items_per_page - 1) // items_per_page

    # Format the inventory for the current page
    page_items = inventory[start_index:end_index]
    inventory_text = "\n".join(
        [
            f"{item.Card.rarity} {index + 1}. {item.Card.name} ({item.Inventory.quantity}x) 📚 {item.Category.name}"
            for index, item in enumerate(page_items, start=start_index + 1)
        ]
    )

    # Fetch the user's nickname
    user_nickname = message.from_user.username or "Treinador"

    # Prepare the message text
    text = (
        f"🎒Uau, @{user_nickname}! encontrei na sua mochila o seguinte pokecard:\n\n"
        f"{inventory_text}\n\n"
        f"Página {page}/{total_pages}"
    )

    # Build inline keyboard for pagination
    keyboard = InlineKeyboardMarkup(row_width=2)
    if page > 1:
        keyboard.add(InlineKeyboardButton("⬅️ Anterior", callback_data=MOCHILA_CALLBACK.format(page=page - 1)))
    if page < total_pages:
        keyboard.add(InlineKeyboardButton("Próximo ➡️", callback_data=MOCHILA_CALLBACK.format(page=page + 1)))

    # Send or edit the message
    if isinstance(message, CallbackQuery):
        await message.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)


@router.callback_query(lambda call: call.data.startswith("mochila_page_"))
async def mochila_pagination_callback(callback: CallbackQuery):
    # Extract the page number from the callback data
    page = int(callback.data.split("_")[-1])

    user_id = callback.from_user.id

    async with get_session() as session:
        # Fetch user inventory
        result = await session.execute(
            select(Inventory, Card, Group, Category)
            .join(Card, Inventory.card_id == Card.id)
            .join(Group, Card.group_id == Group.id)
            .join(Category, Group.category_id == Category.id)
            .where(Inventory.user_id == user_id)
            .order_by(Card.rarity.desc(), Card.name.asc())
        )
        inventory = result.all()

        # Send the requested page
        await send_mochila_page(callback, inventory, page)