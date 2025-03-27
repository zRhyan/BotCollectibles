from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload
from database.models import User, Inventory, Card
from database.session import get_session

router = Router()

@router.message(Command("doar"))
async def doar_command(message: types.Message):
    """
    Handles the /doar command for donating Pokébolas, cards, or captures.
    """
    user_id = message.from_user.id

    # Parse the command arguments
    text_parts = message.text.split(maxsplit=1)
    if len(text_parts) < 2:
        await message.reply(
            "❗ **Erro:** Você precisa especificar o que deseja doar e para quem.\n"
            "Exemplo:\n"
            "`/doar poke 20 nickname`\n"
            "`/doar card * nickname`\n"
            "`/doar 7 x3, 45 x2, 12 x5 nickname`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    args = text_parts[1].strip()

    # Check if the user exists
    async with get_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        donor = result.scalar_one_or_none()

        if not donor:
            await message.reply(
                "❌ **Erro:** Você ainda não está registrado no sistema. Use o comando `/jornada` para começar sua aventura.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Parse donation type
        if args.startswith("poke"):
            await handle_pokeball_donation(args, donor, session, message)
        elif args.startswith("card"):
            await handle_card_donation(args, donor, session, message)
        else:
            await handle_specific_card_donation(args, donor, session, message)


async def handle_pokeball_donation(args, donor, session, message):
    """
    Handles Pokébola donations.
    """
    parts = args.split()
    if len(parts) < 3:
        await message.reply(
            "❗ **Erro:** Você precisa especificar a quantidade de Pokébolas e o nickname do destinatário.\n"
            "Exemplo:\n"
            "`/doar poke 20 nickname`\n"
            "`/doar poke * nickname`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    quantity = parts[1]
    nickname = parts[2]

    # Fetch the recipient
    result = await session.execute(select(User).where(User.nickname == nickname))
    recipient = result.scalar_one_or_none()

    if not recipient:
        await message.reply(
            f"❌ **Erro:** Nenhum usuário encontrado com o nickname `{nickname}`.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Handle donation logic
    if quantity == "*":
        quantity = donor.pokeballs
    else:
        try:
            quantity = int(quantity)
        except ValueError:
            await message.reply(
                "❗ **Erro:** A quantidade deve ser um número inteiro válido ou `*` para doar tudo.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

    if quantity <= 0 or donor.pokeballs < quantity:
        await message.reply(
            f"❌ **Erro:** Você não tem Pokébolas suficientes para doar.\n"
            f"🎯 **Suas Pokébolas:** {donor.pokeballs}",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Confirmation step
    await message.reply(
        f"⚠️ **Confirmação:** Você está prestes a doar `{quantity}` Pokébolas para `{nickname}`.\n"
        "Clique em **Confirmar** para continuar ou ignore esta mensagem para cancelar.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text="✅ Confirmar", callback_data=f"confirm_poke_{quantity}_{nickname}")],
                [types.InlineKeyboardButton(text="❌ Cancelar", callback_data="cancel_donation")]
            ]
        )
    )


async def handle_card_donation(args, donor, session, message):
    """
    Handles card donations (all cards).
    """
    parts = args.split()
    if len(parts) < 3:
        await message.reply(
            "❗ **Erro:** Você precisa especificar o tipo de doação e o nickname do destinatário.\n"
            "Exemplo:\n"
            "`/doar card * nickname`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    nickname = parts[2]

    # Fetch the recipient
    result = await session.execute(select(User).where(User.nickname == nickname))
    recipient = result.scalar_one_or_none()

    if not recipient:
        await message.reply(
            f"❌ **Erro:** Nenhum usuário encontrado com o nickname `{nickname}`.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Fetch donor's inventory
    result = await session.execute(
        select(Inventory).options(joinedload(Inventory.card)).where(Inventory.user_id == donor.id)
    )
    inventory = result.scalars().all()

    if not inventory:
        await message.reply(
            "❌ **Erro:** Você não possui nenhum card para doar.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Confirmation step
    await message.reply(
        f"⚠️ **Confirmação:** Você está prestes a doar todos os seus cards para `{nickname}`.\n"
        "Clique em **Confirmar** para continuar ou ignore esta mensagem para cancelar.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text="✅ Confirmar", callback_data=f"confirm_card_all_{nickname}")],
                [types.InlineKeyboardButton(text="❌ Cancelar", callback_data="cancel_donation")]
            ]
        )
    )


async def handle_specific_card_donation(args, donor, session, message):
    """
    Handles specific card donations (e.g., card IDs with quantities).
    """
    parts = args.rsplit(maxsplit=1)
    if len(parts) < 2:
        await message.reply(
            "❗ **Erro:** Você precisa especificar os IDs dos cards, as quantidades e o nickname do destinatário.\n"
            "Exemplo:\n"
            "`/doar 7 x3, 45 x2, 12 x5 nickname`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    card_data = parts[0]
    nickname = parts[1]

    # Fetch the recipient
    result = await session.execute(select(User).where(User.nickname == nickname))
    recipient = result.scalar_one_or_none()

    if not recipient:
        await message.reply(
            f"❌ **Erro:** Nenhum usuário encontrado com o nickname `{nickname}`.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Parse card data
    donations = []
    for item in card_data.split(","):
        try:
            card_id, quantity = item.strip().split("x")
            card_id = int(card_id)
            quantity = int(quantity)
            donations.append((card_id, quantity))
        except ValueError:
            await message.reply(
                f"❌ **Erro:** Formato inválido para o item `{item}`. Use o formato `ID xQuantidade`.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

    # Confirmation step
    await message.reply(
        f"⚠️ **Confirmação:** Você está prestes a doar os seguintes cards para `{nickname}`:\n"
        + "\n".join([f"- Card ID `{card_id}`: `{quantity}` unidades" for card_id, quantity in donations]) +
        "\n\nClique em **Confirmar** para continuar ou ignore esta mensagem para cancelar.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text="✅ Confirmar", callback_data=f"confirm_specific_{nickname}")],
                [types.InlineKeyboardButton(text="❌ Cancelar", callback_data="cancel_donation")]
            ]
        )
    )