from aiogram import types
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.future import select
from database.session import get_session
from database.models import User

async def pokemart_main_menu(callback_or_message):
    """
    Returns the main Pokémart menu.
    Can handle both callback queries and direct commands.
    """
    user_id = (
        callback_or_message.from_user.id
        if isinstance(callback_or_message, types.CallbackQuery)
        else callback_or_message.from_user.id
    )
    async with get_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            error_message = (
                "❌ **Erro:** Você ainda não está registrado no sistema. Use o comando `/jornada` para começar sua aventura."
            )
            if isinstance(callback_or_message, types.CallbackQuery):
                await callback_or_message.message.edit_text(
                    error_message, parse_mode=ParseMode.MARKDOWN
                )
            else:
                await callback_or_message.reply(
                    error_message, parse_mode=ParseMode.MARKDOWN
                )
            return
        nickname = user.nickname
        coins = user.coins
    text = (
        f"👋 Olá, **{nickname}**! Encontrei alguns produtos à venda, o que deseja comprar?\n\n"
        f"💰 **Suas pokecoins:** {coins}\n\n"
        "Escolha uma das opções abaixo:"
    )
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🎟️ CARDS ESPECIAIS", callback_data="pokemart_event_cards")
    keyboard.button(text="🃏 CAPTURAS", callback_data="pokemart_capturas")
    keyboard.adjust(1)
    if isinstance(callback_or_message, types.CallbackQuery):
        await callback_or_message.message.edit_text(
            text, reply_markup=keyboard.as_markup(), parse_mode=ParseMode.MARKDOWN
        )
    else:
        await callback_or_message.reply(
            text, reply_markup=keyboard.as_markup(), parse_mode=ParseMode.MARKDOWN
        )
