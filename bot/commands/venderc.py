# commands/venderc.py

from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload

from database.session import get_session
from database.models import User, Inventory, Card, Marketplace

# An in-memory dict for pending sales { user_id: [(card_id, qty), ...] }
pending_sales = {}

router = Router()

@router.message(Command("venderc"))
async def venderc_command(message: types.Message):
    print("[DEBUG] ENTER: /venderc handler")  # Always do direct prints

    user_id = message.from_user.id
    # Example command: "/venderc 5 x2, 4 x1"
    text_parts = message.text.split(maxsplit=1)

    if len(text_parts) < 2:
        print("[DEBUG] /venderc has no args => showing usage")
        await message.reply(
            "❗ **Erro:** Você precisa especificar os IDs dos cards e as quantidades para vender.\n"
            "Exemplo:\n"
            "`/venderc 5 x2, 4 x1, 3 x10`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    args = text_parts[1].strip()
    print(f"[DEBUG] /venderc args => {args}")

    # Parse items "ID xQty"
    card_data = args.split(",")
    cards_to_sell = []
    for item in card_data:
        try:
            card_id_str, quantity_str = item.strip().split("x")
            card_id = int(card_id_str)
            qty = int(quantity_str)
            cards_to_sell.append((card_id, qty))
        except ValueError:
            print(f"[DEBUG] Invalid format => {item}")
            await message.reply(
                f"❌ **Erro:** Formato inválido para `{item}`. Use `ID xQuantidade`.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

    # Now fetch user and inventory
    print("[DEBUG] Querying DB for user and inventory")
    try:
        async with get_session() as session:
            user = (await session.execute(
                select(User).where(User.id == user_id)
            )).scalar_one_or_none()

            if not user:
                print(f"[DEBUG] No user found in DB => {user_id}")
                await message.reply(
                    "❌ **Erro:** Você ainda não está registrado. Use `/jornada`.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

            # Load inventory
            inv_result = await session.execute(
                select(Inventory).options(joinedload(Inventory.card))
                .where(Inventory.user_id == user_id)
            )
            user_inventory = inv_result.scalars().all()
            inv_dict = {inv.card_id: inv for inv in user_inventory}

            total_value = 0
            confirmation_text = "⚠️ **Confirmação de Venda**\n\nVocê está prestes a vender:\n\n"

            # Evaluate each card to see if user has it
            rarity_value = {"🥇": 1000, "🥈": 500, "🥉": 250}
            for (card_id, qty) in cards_to_sell:
                inv_item = inv_dict.get(card_id)
                if not inv_item or inv_item.quantity < qty:
                    print(f"[DEBUG] user {user_id} doesn't have enough card {card_id}")
                    await message.reply(
                        f"❌ **Erro:** Você não possui `{qty}` unidades do card ID `{card_id}`.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    return

                card = inv_item.card
                card_val = rarity_value.get(card.rarity, 0) * qty
                total_value += card_val

                confirmation_text += (
                    f"{card.rarity} **{card.id}. {card.name}** - `{qty}` unidades\n"
                    f"💰 Valor parcial: `{card_val}` pokecoins\n\n"
                )

            confirmation_text += f"💵 **Total a receber:** `{total_value}` pokecoins\n\n"
            confirmation_text += "Deseja confirmar a venda?"

            # Store sale for user
            pending_sales[user_id] = cards_to_sell
            print(f"[DEBUG] Built confirmation => total_value={total_value}")

            # Build inline keyboard
            kb = InlineKeyboardBuilder()
            kb.button(text="✅ Vender", callback_data=f"confirm_sell_{user_id}")
            kb.button(text="❌ Cancelar", callback_data="cancel_sell")
            kb.adjust(1)

            await message.reply(
                confirmation_text,
                reply_markup=kb.as_markup(),
                parse_mode=ParseMode.MARKDOWN
            )
            print("[DEBUG] Sent confirmation message with inline keyboard")

    except Exception as e:
        print(f"[DEBUG] EXCEPTION in venderc_command => {e}")
        await message.reply(
            f"❌ **Erro inesperado** => {e}",
            parse_mode=ParseMode.MARKDOWN
        )

@router.callback_query(lambda call: call.data.startswith("confirm_sell_"))
async def confirm_sell(callback: types.CallbackQuery):
    print("[DEBUG] ENTER: confirm_sell callback")
    data_parts = callback.data.split("_")
    if len(data_parts) < 3:
        print("[DEBUG] confirm_sell => invalid callback data")
        await callback.answer("Dados inválidos.", show_alert=True)
        return

    try:
        user_id = int(data_parts[2])
    except ValueError:
        print("[DEBUG] confirm_sell => user_id not integer")
        await callback.answer("Dados inválidos.", show_alert=True)
        return

    if user_id not in pending_sales:
        print("[DEBUG] confirm_sell => no pending sales for user_id")
        await callback.answer("Nenhuma venda pendente encontrada.", show_alert=True)
        return

    cards_to_sell = pending_sales.pop(user_id)
    print(f"[DEBUG] confirm_sell => user {user_id}, cards_to_sell={cards_to_sell}")

    try:
        async with get_session() as session:
            user = (await session.execute(
                select(User).where(User.id == user_id)
            )).scalar_one_or_none()

            if not user:
                print("[DEBUG] confirm_sell => user not found in DB")
                await callback.answer("Usuário não encontrado.", show_alert=True)
                return

            # Re-load inventory
            inv_result = await session.execute(
                select(Inventory).options(joinedload(Inventory.card))
                .where(Inventory.user_id == user_id)
            )
            inv_list = inv_result.scalars().all()
            inv_dict = {i.card_id: i for i in inv_list}

            total_value = 0
            rarity_value = {"🥇": 1000, "🥈": 500, "🥉": 250}

            for (card_id, qty) in cards_to_sell:
                if card_id not in inv_dict or inv_dict[card_id].quantity < qty:
                    print(f"[DEBUG] confirm_sell => not enough card {card_id} for user {user_id}")
                    await callback.answer("❌ Quantidade insuficiente para venda.", show_alert=True)
                    return

                card = inv_dict[card_id].card
                card_val = rarity_value.get(card.rarity, 0) * qty
                total_value += card_val

                inv_dict[card_id].quantity -= qty
                if inv_dict[card_id].quantity <= 0:
                    await session.delete(inv_dict[card_id])

                # Insert marketplace listing
                new_listing = Marketplace(
                    seller_id=user_id,
                    card_id=card_id,
                    price=rarity_value.get(card.rarity, 0)
                )
                session.add(new_listing)

            user.coins += total_value
            await session.commit()

        print(f"[DEBUG] confirm_sell => user {user_id}, earned {total_value}")
        await callback.message.edit_text(
            f"✅ **Venda concluída!** Você recebeu `{total_value}` pokecoins.\n"
            "Os cards agora estão disponíveis no Pokémart.",
            parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer("Venda realizada com sucesso!", show_alert=True)

    except Exception as e:
        print(f"[DEBUG] EXCEPTION in confirm_sell => {e}")
        await callback.answer(f"Erro inesperado => {e}", show_alert=True)

@router.callback_query(lambda call: call.data == "cancel_sell")
async def cancel_sell(callback: types.CallbackQuery):
    print("[DEBUG] ENTER: cancel_sell callback")
    user_id = callback.from_user.id
    if user_id in pending_sales:
        pending_sales.pop(user_id)
        print("[DEBUG] cancel_sell => removed pending sale for user", user_id)

    await callback.message.edit_text("❌ Venda cancelada.", parse_mode=ParseMode.MARKDOWN)
    await callback.answer("Venda cancelada.", show_alert=True)
