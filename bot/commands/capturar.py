# commands/capturar.py

import random
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import InputMediaPhoto, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func
from database.session import get_session
from database.models import User, Card, Inventory, Category, Group

router = Router()

@router.message(Command(commands=["cap", "capturar"]))
async def capturar_command(message: types.Message):
    """
    Handles the initial /cap or /capturar command.
    This command is only available in private chats.
    """
    # Check if the command is being used in a group
    if message.chat.type != "private":
        await message.reply(
            "❌ Este comando não está disponível em grupos.\n"
            "Por favor, use este comando em uma conversa privada com o bot.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    user_id = message.from_user.id

    async with get_session() as session:
        # 1) Check if user exists
        user = await session.get(User, user_id)
        if not user:
            await message.reply(
                "❌ Você não se registrou ainda!\nUse `/jornada` para iniciar sua aventura.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # 2) Check if user has pokebolas
        if user.pokeballs <= 0:
            await message.reply(
                "🎯 **Você está sem pokébolas!**\n"
                "Adquira mais antes de tentar capturar um card.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Fetch all categories
        result = await session.execute(select(Category).order_by(Category.name))
        categories = result.scalars().all()

        if not categories:
            await message.reply(
                "⚠️ Não há categorias disponíveis no momento. Tente novamente mais tarde.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Build inline keyboard with user-specific callback data.
        keyboard = InlineKeyboardBuilder()
        for index, cat in enumerate(categories):
            # Callback data now has the format: choose_cat_{user_id}_{category_id}
            keyboard.button(
                text=cat.name.upper(),
                callback_data=f"choose_cat_{user_id}_{cat.id}"
            )
            if (index + 1) % 2 == 0:
                keyboard.adjust(2)
        # Finalize layout if odd number of buttons
        keyboard.adjust(2)

        msg_text = (
            f"⚡️ @{message.from_user.username or 'Treinador'}, está na hora de capturar! Selecione uma das categorias.\n\n"
            f"🧶 Você tem {user.pokeballs} pokebolas.\n\n"
        )

        await message.answer(
            msg_text,
            reply_markup=keyboard.as_markup(),
            parse_mode=ParseMode.MARKDOWN
        )

@router.callback_query(lambda call: call.data.startswith("choose_cat_"))
async def handle_category_choice(callback: CallbackQuery):
    """
    Handles the user tapping on a category button:
    1) Verifies that the callback is from the correct user.
    2) Deducts 1 pokebola from the user.
    3) Determines the target rarity based on probability.
    4) Selects a random card from that category with the target rarity.
       If no card is found, falls back to any card in that category.
    5) Adds the card to the user's inventory.
    6) Shows the result with an image + stats using the card's actual rarity.
    """
    data_parts = callback.data.split("_")
    # Expected format: "choose_cat_{user_id}_{category_id}"
    if len(data_parts) < 4:
        await callback.answer("Dados inválidos.", show_alert=True)
        return

    expected_user_id = int(data_parts[2])
    if callback.from_user.id != expected_user_id:
        await callback.answer("Você não pode usar este botão.", show_alert=True)
        return

    category_id = int(data_parts[3])
    user_id = callback.from_user.id

    async with get_session() as session:
        # Get the user
        user = await session.get(User, user_id)
        if not user:
            await callback.message.edit_text(
                "❌ Você não se registrou ainda!\nUse `/jornada` para iniciar sua aventura.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        if user.pokeballs <= 0:
            await callback.message.edit_text(
                "🎯 **Você está sem pokébolas!**\n"
                "Adquira mais antes de tentar capturar um card.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Deduct 1 pokebola
        user.pokeballs -= 1
        await session.commit()

        # ---------- Step 2: Determine target rarity based on probability ----------
        # Probabilities: 50% chance for bronze (🥉), 30% for silver (🥈), 20% for gold (🥇)
        roll = random.random()  # 0.0 <= roll < 1.0
        if roll < 0.50:
            target_rarity = "🥉"
        elif roll < 0.80:
            target_rarity = "🥈"
        else:
            target_rarity = "🥇"

        # ---------- Step 3: Get a random card in that category with the target rarity ----------
        card_result = await session.execute(
            select(Card)
            .join(Card.group)
            .where(Group.category_id == category_id, Card.rarity == target_rarity)
            .order_by(func.random())
            .limit(1)
        )
        card = card_result.scalar_one_or_none()

        # If no card found for the target rarity, fallback to any card in that category.
        if not card:
            card_result = await session.execute(
                select(Card)
                .join(Card.group)
                .where(Group.category_id == category_id)
                .order_by(func.random())
                .limit(1)
            )
            card = card_result.scalar_one_or_none()

        if not card:
            await callback.message.edit_text(
                "⚠️ Nenhum card foi encontrado nessa categoria no momento.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # ---------- Step 4: Add the card to the user's inventory ----------
        inv_result = await session.execute(
            select(Inventory).where(
                Inventory.user_id == user_id,
                Inventory.card_id == card.id
            )
        )
        inv_item = inv_result.scalar_one_or_none()

        if inv_item:
            inv_item.quantity += 1
        else:
            new_inv = Inventory(user_id=user_id, card_id=card.id, quantity=1)
            session.add(new_inv)
        await session.commit()

        # ---------- Step 5: Show the result to the user ----------
        category_obj = await session.get(Category, category_id)
        category_name = category_obj.name if category_obj else "Desconhecida"

        user_nickname = callback.from_user.username or "Treinador"
        # Use the actual rarity stored in the card record
        final_rarity = card.rarity

        caption = (
            f"🎰 Que sorte, @{user_nickname}! você acabou de capturar um pokecard.\n\n"
            f"{final_rarity}{card.id}. {card.name} (1x)\n"
            f"📚 {category_name}\n\n"
            f"🃏 Você agora tem {inv_item.quantity if inv_item else 1} deste card.\n\n"
            f"🎒Pokébolas restantes: {user.pokeballs}"
        )

        # If the card has an image stored via Telegram file_id, show it with the caption.
        if card.image_file_id:
            await callback.message.edit_media(
                media=types.InputMediaPhoto(
                    media=card.image_file_id,
                    caption=caption,
                    parse_mode=ParseMode.MARKDOWN
                ),
                reply_markup=None
            )
        else:
            # Fallback to text if no image is available.
            await callback.message.edit_text(
                caption,
                parse_mode=ParseMode.MARKDOWN
            )

# Note:
# Ensure that your bot’s command scope in groups is properly configured to accept commands with a bot username,
# such as `/capturar@BotUsername`, which is important in group settings.
