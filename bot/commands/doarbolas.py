from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from sqlalchemy.future import select
from database.models import User
from database.session import get_session
import logging

# Configure logger
logger = logging.getLogger(__name__)

router = Router()

# Lista de grupos oficiais onde o comando pode ser usado
OFFICIAL_GROUPS = {
    "pokutrocas": -1002618854262,
    "pokutv": -1002618485697,
    "pokurandom": -1002535827033,
    "pokumusica": -1002640439235,
    "pokuasia": -1002582806902,
    "pokuanimagame": -1002521798243,
    "pokuginasio": -1002533762710
}

@router.message(Command("doarbolas"))
async def doarbolas_command(message: types.Message):
    """
    Handles the /doarbolas command for donating Pokébolas.
    Expected format: /doarbolas <quantity|*> <nickname>
    Donation is processed immediately without confirmation.
    """
    # Verificar se o comando está sendo usado em um grupo oficial
    chat = message.chat
    if not chat.username or chat.username.lower() not in OFFICIAL_GROUPS:
        await message.reply(
            "❌ **Este comando só pode ser usado nos grupos oficiais:**\n\n"
            "☀️ GERAL @pokutrocas\n"
            "☀️ TV @pokutv\n"
            "☀️ RANDOM @pokurandom\n"
            "☀️ MÚSICA @pokumusica\n"
            "☀️ ÁSIA @pokuasia\n"
            "☀️ ANIMAGAME @pokuanimagame\n"
            "☀️ GINÁSIO @pokuginasio",
            parse_mode=ParseMode.MARKDOWN
        )
        return
        
    user_id = message.from_user.id

    text_parts = message.text.split(maxsplit=1)
    if len(text_parts) < 2:
        await message.reply(
            "❗ **Erro:** Especifique a quantidade de Pokébolas e o nickname do destinatário.\n"
            "Exemplos:\n"
            "• `/doarbolas 20 nickname`\n"
            "• `/doarbolas * nickname`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    args = text_parts[1].strip()
    parts = args.split()
    if len(parts) < 2:
        await message.reply(
            "❗ **Erro:** Especifique a quantidade de Pokébolas e o nickname do destinatário.\n"
            "Exemplos:\n"
            "• `/doarbolas 20 nickname`\n"
            "• `/doarbolas * nickname`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    quantity = parts[0]
    nickname = parts[1]

    try:
        async with get_session() as session:
            # Fetch donor and recipient in a single session
            donor_result = await session.execute(select(User).where(User.id == user_id))
            donor = donor_result.scalar_one_or_none()
            
            if not donor:
                await message.reply(
                    "❌ **Erro:** Você ainda não está registrado no sistema. Use o comando `/jornada` para começar sua aventura.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

            recipient_result = await session.execute(select(User).where(User.nickname == nickname))
            recipient = recipient_result.scalar_one_or_none()
            
            if not recipient:
                await message.reply(
                    f"❌ **Erro:** Nenhum usuário encontrado com o nickname `{nickname}`.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
                
            if donor.id == recipient.id:
                await message.reply(
                    "❌ **Erro:** Você não pode doar Pokébolas para si mesmo.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

            # Determine donation quantity
            if quantity == "*":
                donation_quantity = donor.pokeballs
            else:
                try:
                    donation_quantity = int(quantity)
                except ValueError:
                    await message.reply(
                        "❗ **Erro:** A quantidade deve ser um número inteiro válido ou `*` para doar tudo.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    return

            if donation_quantity <= 0:
                await message.reply(
                    "❌ **Erro:** A quantidade a doar deve ser maior que zero.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
                
            if donor.pokeballs < donation_quantity:
                await message.reply(
                    f"❌ **Erro:** Você não tem Pokébolas suficientes para doar.\n"
                    f"🎯 **Suas Pokébolas:** {donor.pokeballs}",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
                
            # Executar a transferência de Pokébolas imediatamente
            logger.info(f"Doação de {donation_quantity} pokébolas de {donor.nickname} para {recipient.nickname}")
            donor.pokeballs -= donation_quantity
            recipient.pokeballs += donation_quantity
            await session.commit()
            
            # Enviar mensagem de sucesso
            await message.reply(
                f"✅ **Doação realizada com sucesso!**\n\n"
                f"📦 **Quantidade:** {donation_quantity} Pokébolas\n"
                f"🎁 **Destinatário:** `{recipient.nickname}`\n\n"
                f"📊 **Suas Pokébolas restantes:** {donor.pokeballs}",
                parse_mode=ParseMode.MARKDOWN
            )
            
    except Exception as e:
        logger.error(f"Erro ao processar doação de pokébolas: {str(e)}")
        await message.reply(
            "❌ **Erro:** Ocorreu um problema durante a doação. Tente novamente mais tarde.",
            parse_mode=ParseMode.MARKDOWN
        )
