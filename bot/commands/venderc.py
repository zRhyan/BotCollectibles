from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload
from database.models import User, Inventory, Card, Marketplace
from database.session import get_session

router = Router()

@router.message(Command("venderc"))
async def venderc_command(message: types.Message):
    """
    Handles the /venderc command for selling cards to the Pokémart.
    """
    user_id = message.from_user.id
    text_parts = message.text.split(maxsplit=1)
    if len(text_parts) < 2:
        await message.reply(
            "❗ **Erro:** Você precisa especificar os IDs dos cards e as quantidades para vender.\n"
            "Exemplo:\n"
            "`/venderc 5 x2, 4 x1, 3 x10`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    args = text_parts[1].strip()
    card_data = args.split(",")

    # Parse card data
    cards_to_sell = []
    for item in card_data:
        try:
            card_id, quantity = item.strip().split("x")
            card_id = int(card_id)
            quantity = int(quantity)
            cards_to_sell.append((card_id, quantity))
        except ValueError:
            await message.reply(
                f"❌ **Erro:** Formato inválido para o item `{item}`. Use o formato `ID xQuantidade`.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

    # Fetch user and inventory
    async with get_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            await message.reply(
                "❌ **Erro:** Você ainda não está registrado no sistema. Use o comando `/jornada` para começar sua aventura.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Fetch inventory and validate cards
        result = await session.execute(
            select(Inventory).options(joinedload(Inventory.card)).where(Inventory.user_id == user_id)
        )
        inventory = result.scalars().all()
        inventory_dict = {item.card_id: item for item in inventory}

        total_value = 0
        confirmation_text = "⚠️ **Confirmação de Venda**\n\nVocê está prestes a vender os seguintes cards:\n\n"
        for card_id, quantity in cards_to_sell:
            if card_id not in inventory_dict or inventory_dict[card_id].quantity < quantity:
                await message.reply(
                    f"❌ **Erro:** Você não possui `{quantity}` unidades do card com ID `{card_id}`.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

            card = inventory_dict[card_id].card
            rarity_value = {"🥇": 1000, "🥈": 500, "🥉": 250}
            card_value = rarity_value.get(card.rarity, 0) * quantity
            total_value += card_value

            confirmation_text += (
                f"{card.rarity} **{card.id}. {card.name}** - `{quantity}` unidades\n"
                f"💰 Valor: `{card_value}` pokecoins\n\n"
            )

        confirmation_text += f"💵 **Total a receber:** `{total_value}` pokecoins\n\n"
        confirmation_text += "Deseja confirmar a venda?"

        # Send confirmation message with buttons
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="✅ Vender", callback_data=f"confirm_sell_{user_id}")
        keyboard.button(text="❌ Cancelar", callback_data="cancel_sell")
        keyboard.adjust(1)

        await message.reply(
            confirmation_text,
            reply_markup=keyboard.as_markup(),
            parse_mode=ParseMode.MARKDOWN
        )


@router.callback_query(lambda call: call.data.startswith("confirm_sell_"))
async def confirm_sell(callback: types.CallbackQuery):
    """
    Processes confirmation for selling cards.
    """
    user_id = int(callback.data.split("_")[2])

    async with get_session() as session:
        # Fetch user and inventory
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            await callback.answer("❌ Usuário não encontrado.", show_alert=True)
            return

        result = await session.execute(
            select(Inventory).options(joinedload(Inventory.card)).where(Inventory.user_id == user_id)
        )
        inventory = result.scalars().all()
        inventory_dict = {item.card_id: item for item in inventory}

        # Process the sale
        total_value = 0
        for card_id, quantity in callback.message.text.splitlines():
            if card_id not in inventory_dict or inventory_dict[card_id].quantity < quantity:
                await callback.answer("❌ Erro ao processar a venda.", show_alert=True)
                return

            card = inventory_dict[card_id].card
            rarity_value = {"🥇": 1000, "🥈": 500, "🥉": 250}
            card_value = rarity_value.get(card.rarity, 0) * quantity
            total_value += card_value

            # Deduct from inventory
            inventory_item = inventory_dict[card_id]
            inventory_item.quantity -= quantity
            if inventory_item.quantity == 0:
                await session.delete(inventory_item)

            # Add to marketplace
            new_listing = Marketplace(
                seller_id=user_id,
                card_id=card_id,
                price=rarity_value.get(card.rarity, 0)
            )
            session.add(new_listing)

        # Add coins to user
        user.coins += total_value
        await session.commit()

    await callback.message.edit_text(
        f"✅ **Venda concluída!** Você recebeu `{total_value}` pokecoins.\n"
        "Os cards agora estão disponíveis no Pokémart.",
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer("Venda realizada com sucesso!", show_alert=True)


@router.callback_query(lambda call: call.data == "cancel_sell")
async def cancel_sell(callback: types.CallbackQuery):
    """
    Cancels any pending sale action.
    """
    await callback.message.edit_text("❌ Venda cancelada.", parse_mode=ParseMode.MARKDOWN)
    await callback.answer("Venda cancelada.", show_alert=True)