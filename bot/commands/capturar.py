# commands/capturar.py

import random
import time
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import InputMediaPhoto, InputMediaDocument, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func, update  # Adicionado 'update' aqui
from database.session import get_session
from database.models import User, Card, Inventory, Category, Group
from utils.image_utils import ensure_photo_file_id

router = Router()

# Dicionário para rastrear usuários em processo de captura
# Formato: {user_id: timestamp}
active_captures = {}

# Tempo máximo (em segundos) que um usuário pode ficar no estado de captura
CAPTURE_TIMEOUT = 180  # 3 minutos

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
    current_time = time.time()
    
    # Limpar capturas antigas antes de verificar
    # Isso ajuda a resolver problemas de usuários "travados"
    for uid in list(active_captures.keys()):
        if current_time - active_captures[uid] > CAPTURE_TIMEOUT:
            del active_captures[uid]
    
    # Verificar se o usuário já está em processo de captura
    if user_id in active_captures:
        await message.reply(
            "⚠️ **Você já tem um processo de captura em andamento!**\n"
            "Complete sua captura atual ou aguarde alguns minutos antes de tentar novamente.\n\n"
            "Tempo de espera de **3 minutos** para reinicar o /capturar.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

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
            
        # Marcar usuário como em processo de captura com timestamp atual
        active_captures[user_id] = current_time

        # Build inline keyboard with user-specific callback data
        keyboard = InlineKeyboardBuilder()
        for index, cat in enumerate(categories):
            # Callback data format: choose_cat_{user_id}_{category_id}
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
    2) Retrieves all groups from the chosen category.
    3) Randomly selects up to five distinct groups.
    4) Shows these group options to the user for the next step.
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

        # Retrieve all groups for this category
        groups_result = await session.execute(
            select(Group).where(Group.category_id == category_id)
        )
        all_groups = groups_result.scalars().all()

        if not all_groups:
            await callback.message.edit_text(
                "⚠️ Nenhum grupo encontrado nesta categoria.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Shuffle and slice up to 5 groups
        random.shuffle(all_groups)
        groups_to_show = all_groups[:5]

        # Build an inline keyboard of groups
        keyboard = InlineKeyboardBuilder()
        for index, grp in enumerate(groups_to_show):
            # New callback data format for group selection:
            # choose_group_{user_id}_{category_id}_{group_id}
            keyboard.button(
                text=grp.name.upper(),
                callback_data=f"choose_group_{user_id}_{category_id}_{grp.id}"
            )
            if (index + 1) % 2 == 0:
                keyboard.adjust(2)
        keyboard.adjust(2)

        # Verificar se o usuário ainda está no timeout ativo após verificação de dados
        if user_id not in active_captures:
            await callback.answer("Sua sessão de captura expirou. Inicie uma nova captura.", show_alert=True)
            return

        await callback.message.edit_text(
            text="Selecione um grupo para tentar capturar:",
            reply_markup=keyboard.as_markup(),
            parse_mode=ParseMode.MARKDOWN
        )

@router.callback_query(lambda call: call.data.startswith("choose_group_"))
async def handle_group_choice(callback: CallbackQuery):
    """
    Handles the user tapping on a group button:
    1) Verifies that the callback is from the correct user.
    2) Deducts 1 pokebola from the user.
    3) Determines the target rarity based on probability.
    4) Selects a random card from that group with the target rarity.
       If no card is found, falls back to any card in that group.
    5) Adds the card to the user's inventory.
    6) Shows the result with an image + stats using the card's actual rarity.
    """
    data_parts = callback.data.split("_")
    # Expected format: "choose_group_{user_id}_{category_id}_{group_id}"
    if len(data_parts) < 5:
        await callback.answer("Dados inválidos.", show_alert=True)
        return

    expected_user_id = int(data_parts[2])
    user_id = expected_user_id
    
    if callback.from_user.id != expected_user_id:
        await callback.answer("Você não pode usar este botão.", show_alert=True)
        return

    category_id = int(data_parts[3])
    group_id = int(data_parts[4])
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

        # Determine target rarity based on probability
        roll = random.random()  # 0.0 <= roll < 1.0
        if roll < 0.50:
            target_rarity = "🥉"
        elif roll < 0.80:
            target_rarity = "🥈"
        else:
            target_rarity = "🥇"

        # Get a random card in that group with the target rarity
        card_result = await session.execute(
            select(Card)
            .where(Card.group_id == group_id, Card.rarity == target_rarity)
            .order_by(func.random())
            .limit(1)
        )
        card = card_result.scalar_one_or_none()

        # If no card found for the target rarity, fallback to any card in that group
        if not card:
            card_result = await session.execute(
                select(Card)
                .where(Card.group_id == group_id)
                .order_by(func.random())
                .limit(1)
            )
            card = card_result.scalar_one_or_none()

        if not card:
            await callback.message.edit_text(
                "⚠️ Nenhum card foi encontrado neste grupo no momento.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Add the card to the user's inventory
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

        # Gather information for the caption
        category_obj = await session.get(Category, category_id)
        category_name = category_obj.name if category_obj else "Desconhecida"

        group_obj = await session.get(Group, group_id)
        group_name = group_obj.name if group_obj else "Desconhecido"

        user_nickname = callback.from_user.username or "Treinador"
        final_rarity = card.rarity

        caption = (
            f"🎰 Que sorte, @{user_nickname}! você acabou de capturar um pokecard.\n\n"
            f"{final_rarity}{card.id}. {card.name} (1x)\n"
            f"📚 Categoria: {category_name}\n"
            f"📁 Grupo: {group_name}\n\n"
            f"🃏 Você agora tem {inv_item.quantity if inv_item else 1} deste card.\n\n"
            f"🎒Pokébolas restantes: {user.pokeballs}"
        )

        # Limpar o estado de captura do usuário no final do processo
        if user_id in active_captures:
            del active_captures[user_id]

        # Handle the card's image properly
        if card.image_file_id:
            try:
                # Ensure image has correct aspect ratio
                photo_id = card.image_file_id
                try:
                    # Try to convert and fix aspect ratio if needed
                    photo_id = await ensure_photo_file_id(
                        callback.bot, 
                        types.Document(file_id=card.image_file_id),
                        force_aspect_ratio=True
                    )
                    
                    # Update card's file_id if it changed
                    if photo_id != card.image_file_id:
                        await session.execute(
                            update(Card)
                            .where(Card.id == card.id)
                            .values(image_file_id=photo_id)
                        )
                        await session.commit()
                except Exception:
                    # If conversion fails, use original file_id
                    pass
                
                # Send the image
                await callback.message.edit_media(
                    media=InputMediaPhoto(
                        media=photo_id,
                        caption=caption,
                        parse_mode=ParseMode.MARKDOWN
                    ),
                    reply_markup=None
                )
            except Exception as e:
                # Fallback for any errors
                await callback.message.edit_text(
                    caption,
                    parse_mode=ParseMode.MARKDOWN
                )
        else:
            # Fallback to text if no image is available
            await callback.message.edit_text(
                caption,
                parse_mode=ParseMode.MARKDOWN
            )

# Adicionar função para limpar estados de captura sem atividade (opcional - pode ser implementado futuramente)
# Esta função poderia ser chamada periodicamente por um scheduler para limpar capturas abandonadas
async def clear_abandoned_captures():
    active_captures.clear()
