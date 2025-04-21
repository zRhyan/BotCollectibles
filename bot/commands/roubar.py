import asyncio
import time
import logging
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from database.models import User, Inventory, Card
from database.session import get_session
from database.utils import consolidate_inventory_duplicates

logger = logging.getLogger(__name__)
router = Router()

# Armazenamento global para trocas pendentes
# Cada entrada tem a estrutura:
#   trade_id: {
#       "requester_id": int,
#       "target_id": int,
#       "requested_cards": list[tuple[int, int]],
#       "offered_cards": list[tuple[int, int]],
#       "created_at": float,  # timestamp
#       "processing": bool    # flag para controle de processamento
#   }
pending_trades = {}

# Tempo de expiração (segundos)
TRADE_TIMEOUT = 180  # 3 minutos

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

# ===========================
# Handler principal: /roubar
# ===========================
@router.message(Command(commands=["roubar", "r"]))
async def roubar_command(message: types.Message) -> None:
    """
    Inicia o fluxo de troca de cartas entre dois usuários.
    Sintaxe esperada (exemplo):
      /roubar @usuario_alvo 20 2, 25 1 | 10 3, 42 2

    Apenas o usuário–alvo poderá aceitar ou recusar a troca.
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
        
    requester_id = message.from_user.id
    logger.info("Comando /roubar recebido do usuário %s", requester_id)
    text_parts = message.text.strip().split(maxsplit=1)
    if len(text_parts) < 2:
        await message.reply(
            "❗ **Uso incorreto:**\nExemplo: `/roubar @Fulano 20 2, 25 1 | 10 3, 42 2`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    remainder_list = text_parts[1].split()
    if not remainder_list:
        await message.reply("❗ **Erro:** Argumentos insuficientes.", parse_mode=ParseMode.MARKDOWN)
        return

    # Extrai o @username do alvo
    possible_mention = remainder_list[0]
    target_mention = None
    if possible_mention.startswith("@"):
        target_mention = possible_mention
        remainder_list = remainder_list[1:]
    else:
        # Se não houver menção, tenta extrair a partir da mensagem respondida
        if message.reply_to_message and message.reply_to_message.from_user:
            target_mention = "@" + (message.reply_to_message.from_user.username or "")
        else:
            await message.reply(
                "❗ **Erro:** Forneça @username do alvo ou responda a mensagem dele.\nEx: `/roubar @user 20 2, 25 1 | 10 3, 42 2`",
                parse_mode=ParseMode.MARKDOWN
            )
            return

    if not remainder_list:
        await message.reply("❗ **Erro:** Faltam as cartas.", parse_mode=ParseMode.MARKDOWN)
        return

    all_cards_str = " ".join(remainder_list)
    # Permite os delimitadores '|' ou 'x'
    delim_pos = None
    used_delim = None
    for delim in ("|", "x"):
        pos = all_cards_str.find(delim)
        if pos != -1:
            delim_pos = pos
            used_delim = delim
            break

    if delim_pos is None:
        await message.reply(
            "❗ **Erro:** Formato inválido. Use '|' ou 'x' para separar o que deseja e o que oferece.\nEx: `/roubar @Fulano 20 2, 25 1 | 10 3, 42 2`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    left_part = all_cards_str[:delim_pos].strip()
    right_part = all_cards_str[delim_pos + 1:].strip()  # Corrigido de .trip() para .strip()

    if not left_part or not right_part:
        await message.reply(
            "❗ **Erro:** Partes vazias antes/depois do delimitador.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    try:
        requested_cards = parse_card_data(left_part)
        offered_cards = parse_card_data(right_part)
    except ValueError as ve:
        logger.error("Erro no parsing das cartas: %s", ve)
        await message.reply(f"❗ **Erro de Formato:** {ve}", parse_mode=ParseMode.MARKDOWN)
        return

    # Busca o usuário–alvo no banco de dados
    async with get_session() as session:
        target_user = await find_user_by_mention(session, target_mention)
        if not target_user:
            await message.reply(
                f"❌ **Erro:** Usuário `{target_mention}` não encontrado.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        target_id = target_user.id

    # Monta o texto da proposta de troca
    request_text = await build_trade_text(requested_cards, offered_cards)
    confirm_text = (
        f"🔁 **Pedido de troca:**\n\n"
        f"👤 Solicitante: {message.from_user.username or requester_id}\n"
        f"🎯 Alvo: {target_mention}\n\n"
        f"{request_text}\n"
        "Clique em **Aceitar** para confirmar ou **Recusar** para cancelar."
    )

    # Cria o teclado inline com callback_data que contém o ID único da troca.
    # Usaremos o ID da mensagem enviada com o teclado como identificador único.
    sent_message = await message.reply(
        confirm_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Aceitar", callback_data=f"roubar_accept:{sent_message_id_placeholder()}"),
                    InlineKeyboardButton(text="❌ Recusar", callback_data=f"roubar_reject:{sent_message_id_placeholder()}")
                ]
            ]
        )
    )
    # Utiliza o ID da mensagem enviada como trade_id
    trade_id = sent_message.message_id

    # Agora, atualizamos o teclado inline com o trade_id correto
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Aceitar", callback_data=f"roubar_accept:{trade_id}"),
                InlineKeyboardButton(text="❌ Recusar", callback_data=f"roubar_reject:{trade_id}")
            ]
        ]
    )
    try:
        await sent_message.edit_reply_markup(reply_markup=kb)
    except Exception as e:
        logger.error("Erro ao atualizar teclado inline: %s", e)

    # Armazena os dados da troca com timestamp
    pending_trades[trade_id] = {
        "requester_id": requester_id,
        "target_id": target_id,
        "requested_cards": requested_cards,
        "offered_cards": offered_cards,
        "created_at": time.time(),
        "processing": False  # Adicionado flag para controle de processamento
    }
    logger.info("Troca pendente criada (trade_id=%s) entre %s e %s", trade_id, requester_id, target_id)

    # Auto-limpeza: remove a troca após o timeout, se ainda estiver pendente.
    async def auto_cleanup(trade_id: int, chat_id: int):
        await asyncio.sleep(TRADE_TIMEOUT)
        trade_data = pending_trades.get(trade_id)
        if trade_data:
            logger.info("Troca %s expirada após %s segundos", trade_id, TRADE_TIMEOUT)
            del pending_trades[trade_id]
            try:
                # Se possível, edita a mensagem para informar que a proposta expirou.
                await sent_message.edit_text(
                    "⌛ A proposta de troca expirou após 3 minutos sem resposta.",
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                logger.error("Erro ao editar mensagem expirada (trade_id=%s): %s", trade_id, e)
            # Opcional: enviar uma mensagem de notificação no chat
            try:
                await message.bot.send_message(
                    chat_id,
                    "⌛ A proposta de troca expirou.",
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                logger.error("Erro ao notificar expiração da troca (trade_id=%s): %s", trade_id, e)

    asyncio.create_task(auto_cleanup(trade_id, message.chat.id))


# ===============================
# Handler para ACEITAR a troca
# ===============================
@router.callback_query(F.data.startswith("roubar_accept:"))
async def roubar_accept_callback(callback: CallbackQuery) -> None:
    """
    Executa a troca quando o usuário–alvo clica em "Aceitar".
    Valida se a troca ainda está ativa, se o usuário é o alvo e então processa a transação.
    """
    logger.info("Callback ACEITAR recebido de %s", callback.from_user.id)
    try:
        _, trade_id_str = callback.data.split(":")
        trade_id = int(trade_id_str)
    except Exception as e:
        logger.error("Erro ao interpretar callback_data (%s): %s", callback.data, e)
        await callback.answer("Dados de troca inválidos.", show_alert=True)
        return

    trade_data = pending_trades.get(trade_id)
    if not trade_data:
        logger.warning("Troca não encontrada ou expirada (trade_id=%s)", trade_id)
        await callback.answer("Troca expirada ou inválida.", show_alert=True)
        return

    # Verifica expiração
    if time.time() - trade_data["created_at"] > TRADE_TIMEOUT:
        logger.info("Troca %s expirada", trade_id)
        del pending_trades[trade_id]
        await callback.answer("Troca expirada.", show_alert=True)
        return

    # Verifica se o clique é feito pelo usuário–alvo
    if callback.from_user.id != trade_data["target_id"]:
        logger.warning("Usuário %s tentou interagir com a troca %s (alvo=%s)",
                       callback.from_user.id, trade_id, trade_data["target_id"])
        await callback.answer("Você não pode interagir com essa troca.", show_alert=True)
        return
        
    # Verifica se a troca já está sendo processada (evita cliques múltiplos)
    if trade_data.get("processing", False):
        logger.warning("Tentativa de processar troca %s que já está em processamento", trade_id)
        await callback.answer("Esta troca já está sendo processada.", show_alert=True)
        return
        
    # Marca imediatamente a troca como em processamento
    trade_data["processing"] = True

    # Processa a troca
    requester_id = trade_data["requester_id"]
    requested_cards = trade_data["requested_cards"]
    offered_cards = trade_data["offered_cards"]

    try:
        async with get_session() as session:
            # Carrega o solicitante e seu inventário
            req_result = await session.execute(
                select(User).where(User.id == requester_id).options(joinedload(User.inventory))
            )
            requester = req_result.unique().scalar_one_or_none()

            # Carrega o usuário–alvo (quem aceitou)
            tgt_result = await session.execute(
                select(User).where(User.id == callback.from_user.id).options(joinedload(User.inventory))
            )
            target_user = tgt_result.unique().scalar_one_or_none()

            if not requester or not target_user:
                logger.error("Usuário não encontrado: requester(%s) ou target(%s)",
                             requester_id, callback.from_user.id)
                await callback.answer("Usuário não encontrado ou não registrado.", show_alert=True)
                return
                
            # Consolidar possíveis duplicatas de inventário para ambos os usuários
            await consolidate_inventory_duplicates(session, requester_id)
            await consolidate_inventory_duplicates(session, callback.from_user.id)

            # Recarregar o inventário após consolidação para ter os dados mais atualizados
            await session.refresh(requester, ["inventory"])
            await session.refresh(target_user, ["inventory"])

            # Verifica se o alvo possui as cartas solicitadas
            for (card_id, qty) in requested_cards:
                t_item = next((inv for inv in target_user.inventory if inv.card_id == card_id), None)
                if not t_item or t_item.quantity < qty:
                    msg = f"Você não possui {qty}x do card ID {card_id}."
                    logger.info("Troca falhou: %s", msg)
                    await callback.answer(msg, show_alert=True)
                    return

            # Verifica se o solicitante possui as cartas ofertadas
            for (card_id, qty) in offered_cards:
                r_item = next((inv for inv in requester.inventory if inv.card_id == card_id), None)
                if not r_item or r_item.quantity < qty:
                    msg = f"O solicitante não possui {qty}x do card ID {card_id}."
                    logger.info("Troca falhou: %s", msg)
                    await callback.answer(msg, show_alert=True)
                    return

            # Transfere os cards do alvo para o solicitante
            for (card_id, qty) in requested_cards:
                t_item = next(inv for inv in target_user.inventory if inv.card_id == card_id)
                t_item.quantity -= qty
                r_item = next((inv for inv in requester.inventory if inv.card_id == card_id), None)
                if r_item:
                    r_item.quantity += qty
                else:
                    session.add(Inventory(user_id=requester_id, card_id=card_id, quantity=qty))

            # Transfere os cards do solicitante para o alvo
            for (card_id, qty) in offered_cards:
                r_item = next(inv for inv in requester.inventory if inv.card_id == card_id)
                r_item.quantity -= qty
                t_item = next((inv for inv in target_user.inventory if inv.card_id == card_id), None)
                if t_item:
                    t_item.quantity += qty
                else:
                    session.add(Inventory(user_id=callback.from_user.id, card_id=card_id, quantity=qty))

            await session.commit()
            logger.info("Troca %s concluída com sucesso.", trade_id)
    except Exception as e:
        logger.exception("Erro durante processamento da troca (trade_id=%s): %s", trade_id, e)
        await callback.answer("Erro interno durante a troca.", show_alert=True)
        return

    try:
        await callback.message.edit_text("✅ **Troca concluída com sucesso!**", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error("Erro ao editar mensagem da troca (trade_id=%s): %s", trade_id, e)
    await callback.answer("Troca finalizada!", show_alert=True)
    # Remove a troca dos registros pendentes
    pending_trades.pop(trade_id, None)


# ===============================
# Handler para RECUSAR a troca
# ===============================
@router.callback_query(F.data.startswith("roubar_reject:"))
async def roubar_reject_callback(callback: CallbackQuery) -> None:
    """
    Cancela a troca quando o usuário–alvo clica em "Recusar".
    """
    logger.info("Callback RECUSAR recebido de %s", callback.from_user.id)
    try:
        _, trade_id_str = callback.data.split(":")
        trade_id = int(trade_id_str)
    except Exception as e:
        logger.error("Erro ao interpretar callback_data (%s): %s", callback.data, e)
        await callback.answer("Dados de troca inválidos.", show_alert=True)
        return

    trade_data = pending_trades.get(trade_id)
    if not trade_data:
        logger.warning("Troca não encontrada ou expirada (trade_id=%s)", trade_id)
        await callback.answer("Troca expirada ou inválida.", show_alert=True)
        return

    # Verifica se o clique é feito pelo usuário–alvo
    if callback.from_user.id != trade_data["target_id"]:
        logger.warning("Usuário %s tentou interagir com a troca %s (alvo=%s)",
                       callback.from_user.id, trade_id, trade_data["target_id"])
        await callback.answer("Você não pode interagir com essa troca.", show_alert=True)
        return

    logger.info("Troca %s recusada pelo usuário %s", trade_id, callback.from_user.id)
    try:
        await callback.message.edit_text("❌ **Troca recusada.**", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error("Erro ao editar mensagem de recusa (trade_id=%s): %s", trade_id, e)
    await callback.answer("Troca recusada.", show_alert=True)
    pending_trades.pop(trade_id, None)


# =========================================================
# Funções auxiliares
# =========================================================

async def build_trade_text(
    requested_cards: list[tuple[int, int]],
    offered_cards: list[tuple[int, int]]
) -> str:
    """
    Constrói a mensagem com a listagem dos cards desejados e ofertados,
    buscando informações de nome e raridade no banco de dados.
    """
    all_ids = {cid for (cid, _) in requested_cards} | {cid for (cid, _) in offered_cards}
    if not all_ids:
        return "Nenhuma carta listada."

    async with get_session() as session:
        stmt = select(Card).where(Card.id.in_(all_ids))
        res = await session.execute(stmt)
        card_objs = res.scalars().all()

    card_map = {c.id: (c.name, c.rarity) for c in card_objs}

    requested_lines = []
    for cid, qty in requested_cards:
        name, rarity = card_map.get(cid, ("??", "??"))
        requested_lines.append(f"- {cid}. {rarity}{name} ({qty}x)")

    offered_lines = []
    for cid, qty in offered_cards:
        name, rarity = card_map.get(cid, ("??", "??"))
        offered_lines.append(f"- {cid}. {rarity}{name} ({qty}x)")

    text = (
        "✨ **Cartas desejadas:**\n" + "\n".join(requested_lines) + "\n\n" +
        "🎁 **Cartas ofertadas:**\n" + "\n".join(offered_lines) + "\n"
    )
    return text


def parse_card_data(card_block: str) -> list[tuple[int, int]]:
    """
    Faz o parse de um bloco de texto com o formato:
        card_id quantidade, card_id quantidade
    Exemplo: "20 2, 25 1" => [(20, 2), (25, 1)]
    """
    pairs = card_block.split(",")
    cards = []
    for chunk in pairs:
        chunk = chunk.strip()  # Corrigido de trip() para strip()
        if not chunk:
            continue
        tokens = chunk.split()
        if len(tokens) != 2:
            raise ValueError(f"Bloco inválido: '{chunk}'. Use 'ID QTD' e separe com vírgulas. Ex: '20 2, 25 1'.")
        try:
            cid = int(tokens[0])
            qty = int(tokens[1])
            if qty <= 0:
                raise ValueError(f"Quantidade inválida em '{chunk}' (deve ser > 0).")
            cards.append((cid, qty))
        except ValueError as e:
            raise ValueError(f"Erro ao interpretar '{chunk}': {e}")
    return cards


async def find_user_by_mention(session, mention: str) -> User | None:
    """
    Busca um usuário cujo username ou nickname (case-insensitive)
    combine com a menção fornecida (ex: '@Fulano').
    """
    mention_clean = mention.lstrip("@").lower()
    stmt = select(User).where(
        (User.username == mention_clean) |
        (User.nickname.ilike(f"%{mention_clean}%"))
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


def sent_message_id_placeholder() -> str:
    """
    Função auxiliar para compor o placeholder inicial do callback_data.
    Esse valor será substituído logo após o envio da mensagem.
    """
    return "0"
