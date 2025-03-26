# commands/capturar.py

import random
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from sqlalchemy import select, func
from database.session import get_session
from database.models import User, Card, Inventory, Category

router = Router()

@router.message(Command(commands=["cap", "capturar"]))
async def capturar_command(message: types.Message):
    """
    Handles the initial /cap or /capturar command.
    1) Check if user is registered
    2) Check if user has pokebolas
    3) Show an inline keyboard of categories
    """

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

        # Build inline keyboard
        # We'll arrange categories in pairs per row, for a neat layout
        keyboard = InlineKeyboardBuilder()
        for index, cat in enumerate(categories):
            keyboard.button(
                text=cat.name.upper(),
                callback_data=f"choose_cat_{cat.id}"
            )
            # After placing 2 buttons in a row, start a new row
            if (index + 1) % 2 == 0:
                keyboard.adjust(2)

        # If there's an odd number of categories, finalize the layout
        keyboard.adjust(2)

        msg_text = (
            "⚡️ Está na hora de capturar! Selecione uma das categorias.\n\n"
            f"🧶 Você tem {user.pokeballs} pokebolas.\n\n"
        )

        await message.answer(
            msg_text,
            reply_markup=keyboard.as_markup(),
            parse_mode=ParseMode.MARKDOWN
        )

@capturar_router.callback_query(lambda call: call.data.startswith("choose_cat_"))
async def handle_category_choice(callback: CallbackQuery):
    """
    Handles the user tapping on a category button:
    1) Deduct 1 pokebola from the user
    2) Determine card rarity by random probability
    3) Select a random card of that category with that rarity
    4) Add card to user's inventory
    5) Show the result with an image + stats
    """
    user_id = callback.from_user.id
    data_parts = callback.data.split("_")
    # e.g. "choose_cat_13" => ["choose","cat","13"]
    category_id = int(data_parts[2])  # in this example, 13

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

        # Save now, just in case
        await session.commit()

        # ---------- Step 2: Determine rarity by random probability ----------
        # e.g. common=40%, uncommon=30%, rare=20%, epic=10%
        roll = random.random()  # 0.0 <= roll < 1.0
        if roll < 0.40:
            chosen_rarity = "Common"
        elif roll < 0.70:
            chosen_rarity = "Uncommon"
        elif roll < 0.90:
            chosen_rarity = "Rare"
        else:
            chosen_rarity = "Epic"

        # ---------- Step 3: Get a random card in the chosen category & rarity ----------
        card_result = await session.execute(
            select(Card)
            .where((Card.category_id == category_id) & (Card.rarity == chosen_rarity))
            .order_by(func.random())
            .limit(1)
        )
        card = card_result.scalar_one_or_none()

        # If no card found for that rarity, fallback to ANY card in that category
        if not card:
            card_result = await session.execute(
                select(Card)
                .where(Card.category_id == category_id)
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
        # e.g. send an image + caption with card data
        category_obj = await session.get(Category, category_id)
        category_name = category_obj.name if category_obj else "Desconhecida"

        caption = (
            f"🎉 *Parabéns!* Você capturou:\n\n"
            f"🆔 **ID**: {card.id}\n"
            f"🃏 **Nome**: {card.name}\n"
            f"📂 **Categoria**: {category_name}\n"
            f"✨ **Raridade**: {card.rarity}\n\n"
            f"🔑 Suas pokebolas restantes: {user.pokeballs}"
        )

        # If you store card images via Telegram file_id
        # or if you have an external URL
        if card.image_file_id:
            await callback.message.edit_media(
                media=types.InputMediaPhoto(
                    media=card.image_file_id,
                    caption=caption
                ),
                reply_markup=None
            )
        else:
            # If no image, just edit the text
            await callback.message.edit_text(
                caption,
                parse_mode=ParseMode.MARKDOWN
            )
