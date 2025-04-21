from aiogram import Router, types, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from database.models import User, Inventory, Card
from database.session import get_session, run_transaction
from database.utils import consolidate_inventory_duplicates
import logging

# Configure logger
logger = logging.getLogger(__name__)

router = Router()

# Lista de grupos oficiais onde o comando pode ser usado
OFFICIAL_GROUPS = {
    "pokutrocas": -1002618854262,  # IDs dos grupos serão adicionados aqui
    "pokutv": -1002618485697,
    "pokurandom": -1002535827033,
    "pokumusica": -1002640439235,
    "pokuasia": -1002582806902,
    "pokuanimagame": -1002521798243,
    "pokuginasio": -1002533762710
}

@router.message(Command(commands=["doarcards"]))
async def doarcards_command(message: types.Message, state: FSMContext) -> None:
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

    # Verifica se já existe um fluxo ativo no FSM
    if await state.get_state():
        await message.reply(
            "⚠️ Você já possui uma doação em andamento. Conclua ou cancele o fluxo atual antes de iniciar outra.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    donor_id = message.from_user.id
    
    # Atualizar o nome de usuário no banco de dados se o usuário mudou de @username
    async with get_session() as session:
        # Silently update username if it changed
        if message.from_user.username:
            await update_username_if_changed(session, donor_id, message.from_user.username)
    
    nickname = None
    cards_input = None
    recipient_id = None

    # Verifica se é uma resposta a uma mensagem
    if message.reply_to_message:
        replied_user = message.reply_to_message.from_user
        if replied_user.id == donor_id:
            await message.reply(
                "❗ Você não pode doar cards para si mesmo.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
            
        # Buscar o destinatário usando a nova função aprimorada
        async with get_session() as session:
            # Use o ID do usuário respondido para buscar diretamente no banco
            recipient = await session.get(User, replied_user.id)
            
            if not recipient:
                await message.reply(
                    "❌ **Erro:** O usuário que você respondeu ainda não está registrado no bot.\n"
                    "Peça para ele usar o comando /jornada primeiro!",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            
            recipient_id = recipient.id    
            nickname = recipient.nickname
            # Pegando apenas os cards quando for resposta (removendo o /doarcards)
            cards_input = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else "*"
    else:
        # Formato antigo: /doarcards <cards> <nickname/username>
        text_parts = message.text.split(maxsplit=1)
        if len(text_parts) < 2:
            await message.reply(
                "❗ **Uso do comando:**\n\n"
                "1️⃣ Responda a mensagem de alguém com:\n"
                "• `/doarcards *` para doar todos os seus cards\n"
                "• `/doarcards 7 x3, 45 x2` para doar cards específicos\n\n"
                "2️⃣ Ou use o formato tradicional:\n"
                "• `/doarcards * nickname` ou `/doarcards * @username`\n"
                "• `/doarcards 7 x3, 45 x2 nickname` ou `/doarcards 7 x3, 45 x2 @username`",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        args = text_parts[1].strip()
        if "*" in args:
            # Format: /doarcards * <nickname or @username>
            parts = args.split()
            if len(parts) < 2:
                await message.reply(
                    "❗ **Erro:** Especifique o nickname ou @username do destinatário.\n"
                    "Exemplo: `/doarcards * nickname` ou `/doarcards * @username`",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            cards_input = "*"
            recipient_reference = parts[1]  # Pode ser nickname ou @username
            
            # Buscar o usuário pelo nickname ou username
            async with get_session() as session:
                recipient = await find_user_by_reference(session, recipient_reference, message_user_id=donor_id)
                if not recipient:
                    await message.reply(
                        f"❌ **Erro:** Nenhum usuário encontrado com o nome `{recipient_reference}`.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    return
                nickname = recipient.nickname
                recipient_id = recipient.id
        else:
            # Format: /doarcards <card_id xQuant, ...> <nickname or @username>
            parts = args.rsplit(maxsplit=1)
            if len(parts) < 2:
                await message.reply(
                    "❗ **Erro:** Especifique os IDs dos cards, as quantidades e o nickname/username do destinatário.\n"
                    "Exemplo: `/doarcards 7 x3, 45 x2 nickname` ou `/doarcards 7 x3, 45 x2 @username`",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            cards_input = parts[0]
            recipient_reference = parts[1]  # Pode ser nickname ou @username
            
            # Buscar o usuário pelo nickname ou username
            async with get_session() as session:
                recipient = await find_user_by_reference(session, recipient_reference, message_user_id=donor_id)
                if not recipient:
                    await message.reply(
                        f"❌ **Erro:** Nenhum usuário encontrado com o nome `{recipient_reference}`.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    return
                nickname = recipient.nickname
                recipient_id = recipient.id

    # A partir daqui, temos nickname, recipient_id e cards_input definidos
    if recipient_id == donor_id:
        await message.reply(
            "❗ Você não pode doar cards para si mesmo.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    if cards_input == "*":
        # Processar doação de todos os cards imediatamente
        async def transfer_all_cards(session):
            # Carregar dados do doador e destinatário
            donor_result = await session.execute(
                select(User).where(User.id == donor_id).options(joinedload(User.inventory))
            )
            donor = donor_result.unique().scalar_one_or_none()

            recipient_result = await session.execute(
                select(User).where(User.id == recipient_id)
            )
            recipient = recipient_result.scalar_one_or_none()
            
            if not donor or not recipient:
                return {"success": False, "error": "Usuário não encontrado"}
                
            if donor.id == recipient.id:
                return {"success": False, "error": "Não é possível doar para si mesmo"}
            
            # Consolidar possíveis duplicatas do doador e destinatário antes de processar
            await consolidate_inventory_duplicates(session, donor.id)
            await consolidate_inventory_duplicates(session, recipient.id)
            
            # Lista de cards doados para mensagem de sucesso
            donated_cards = []
            
            # Transferir todos os cards
            for inv_item in donor.inventory:
                if inv_item.quantity > 0:
                    donated_cards.append((inv_item.card_id, inv_item.quantity))
                    # Buscar ou criar entrada no inventário do destinatário
                    rec_inv_result = await session.execute(
                        select(Inventory).where(
                            Inventory.user_id == recipient.id,
                            Inventory.card_id == inv_item.card_id
                        )
                    )
                    recipient_inv = rec_inv_result.scalar_one_or_none()
                    if recipient_inv:
                        recipient_inv.quantity += inv_item.quantity
                    else:
                        new_inv = Inventory(
                            user_id=recipient.id,
                            card_id=inv_item.card_id,
                            quantity=inv_item.quantity
                        )
                        session.add(new_inv)
                    inv_item.quantity = 0
            
            return {"success": True, "donated_cards": donated_cards}
            
        # Executar operação em transação segura
        success, result, error = await run_transaction(
            transfer_all_cards,
            "Erro ao transferir cards"
        )
        
        if not success or not result or result.get("success") is False:
            error_msg = error or result.get("error", "Erro desconhecido")
            await message.reply(
                f"❌ **Doação falhou:** {error_msg}",
                parse_mode=ParseMode.MARKDOWN
            )
            return
            
        # Gerar mensagem de sucesso
        donated_cards = result.get("donated_cards", [])
        if donated_cards:
            cards_list = "\n".join([f"- Card ID `{card_id}`: `{quantity}` unidades" for card_id, quantity in donated_cards])
            await message.reply(
                f"✅ **Doação realizada com sucesso!**\n\n"
                f"**Cards doados:**\n{cards_list}\n\n"
                f"**Destinatário:** `{nickname}`",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await message.reply(
                f"✅ **Doação realizada com sucesso!**\n\n"
                f"Você não possuía nenhum card para doar a `{nickname}`.",
                parse_mode=ParseMode.MARKDOWN
            )

    else:
        # Processar doação específica
        card_data = cards_input

        # Análise da string de doações
        donations: list[tuple[int, int]] = []
        for item in card_data.split(","):
            try:
                item = item.strip()
                if "x" not in item:
                    await message.reply(
                        f"❌ **Erro:** Formato inválido para o item `{item}`. Use `ID xQuantidade`.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    return
                    
                card_id_str, quantity_str = item.split("x")
                card_id = int(card_id_str.strip())
                quantity = int(quantity_str.strip())
                if quantity <= 0:
                    await message.reply(
                        f"❌ **Erro:** Quantidade inválida em `{item}`.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    return
                donations.append((card_id, quantity))
            except ValueError:
                await message.reply(
                    f"❌ **Erro:** Formato inválido para o item `{item}`. Use `ID xQuantidade`.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

        # Process the donation of specific cards
        async def transfer_specific_cards(session):
            # Load donor and recipient data with card details
            donor_result = await session.execute(
                select(User).where(User.id == donor_id)
                .options(joinedload(User.inventory).joinedload(Inventory.card))
            )
            donor = donor_result.unique().scalar_one_or_none()

            recipient_result = await session.execute(
                select(User).where(User.id == recipient_id)
            )
            recipient = recipient_result.scalar_one_or_none()
            
            if not donor or not recipient:
                return {"success": False, "error": "Usuário não encontrado"}
                
            if donor.id == recipient.id:
                return {"success": False, "error": "Não é possível doar para si mesmo"}
            
            # Consolidar possíveis duplicatas do doador e destinatário antes de processar
            await consolidate_inventory_duplicates(session, donor.id)
            await consolidate_inventory_duplicates(session, recipient.id)
            
            # First, verify if the user has all the necessary cards
            invalid_donations = []
            cards_info = []
            total_cards = 0
            
            for card_id, quantity in donations:
                donor_inv = next((inv for inv in donor.inventory if inv.card_id == card_id), None)
                if not donor_inv or donor_inv.quantity < quantity:
                    invalid_donations.append((card_id, quantity))
                else:
                    card_info = {
                        "id": card_id,
                        "name": donor_inv.card.name,
                        "rarity": donor_inv.card.rarity,
                        "quantity": quantity
                    }
                    cards_info.append(card_info)
                    total_cards += quantity
            
            if invalid_donations:
                invalid_list = ", ".join([f"ID {card_id} (x{quantity})" 
                                        for card_id, quantity in invalid_donations])
                return {
                    "success": False, 
                    "error": f"Quantidade insuficiente dos seguintes cards: {invalid_list}"
                }
            
            # Transfer the specified cards
            for card_id, quantity in donations:
                donor_inv = next((inv for inv in donor.inventory if inv.card_id == card_id), None)
                donor_inv.quantity -= quantity

                rec_inv_result = await session.execute(
                    select(Inventory).where(
                        Inventory.user_id == recipient.id,
                        Inventory.card_id == card_id
                    )
                )
                recipient_inv = rec_inv_result.scalar_one_or_none()
                if recipient_inv:
                    recipient_inv.quantity += quantity
                else:
                    new_inv = Inventory(
                        user_id=recipient.id,
                        card_id=card_id,
                        quantity=quantity
                    )
                    session.add(new_inv)
            
            return {
                "success": True, 
                "donated_cards": cards_info,
                "total_cards": total_cards
            }
        
        # Execute operation in a safe transaction
        success, result, error = await run_transaction(
            transfer_specific_cards,
            "Erro ao transferir cards específicos"
        )
        
        if not success or not result or result.get("success") is False:
            error_msg = error or result.get("error", "Erro desconhecido")
            await message.reply(
                f"❌ **Doação falhou:** {error_msg}",
                parse_mode=ParseMode.MARKDOWN
            )
            return
            
        # Generate success message with detailed card information
        donated_cards = result.get("donated_cards", [])
        total_cards = result.get("total_cards", 0)
        
        if donated_cards:
            cards_list = "\n".join([
                f"{card['rarity']}{card['id']}. {card['name']} ({card['quantity']}x)"
                for card in donated_cards
            ])
            
            await message.reply(
                f"✨ **Doação realizada com sucesso!** ✨\n\n"
                f"📦 **Cards doados ({total_cards} no total):**\n{cards_list}\n\n"
                f"🎁 **Destinatário:** `{nickname}`\n\n"
                f"_Que sua generosidade traga muita alegria ao colecionador!_ 🌟",
                parse_mode=ParseMode.MARKDOWN
            )

async def find_user_by_reference(session, reference: str, message_user_id: int = None) -> User | None:
    """
    Enhanced function to find a user by @username, nickname, or from a message reference.
    Also updates the database if the username has changed.
    
    Args:
        session: Database session
        reference: Username with @ or nickname without @
        message_user_id: Current user's ID to avoid self-references
        
    Returns:
        User object or None if not found
    """
    # Clean up reference (remove @ if present)
    reference_clean = reference.lstrip("@").lower()
    
    # Try to find by username OR nickname case-insensitive
    stmt = select(User).where(
        (User.username.ilike(reference_clean)) | 
        (User.nickname.ilike(f"%{reference_clean}%"))
    )
    
    # Exclude self if message_user_id is provided
    if message_user_id is not None:
        stmt = stmt.where(User.id != message_user_id)
        
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def update_username_if_changed(session, user_id: int, current_username: str) -> None:
    """
    Updates the user's username in the database if it has changed.
    
    Args:
        session: Database session
        user_id: Telegram user ID
        current_username: Current Telegram username
    """
    if not current_username:
        return  # Skip if no username provided
        
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    
    if user and user.username != current_username:
        logger.info(f"Updating username for user {user_id} from '{user.username}' to '{current_username}'")
        user.username = current_username
        await session.commit()
