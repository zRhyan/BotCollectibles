import asyncio
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from database.models import User, Inventory, Card
from database.session import get_session

router = Router()

# Armazenamento temporário para trocas pendentes
pending_trades = {}

# ===========================
# Definição de estado via FSM
# ===========================
class RoubarStates(StatesGroup):
    WAITING_TARGET_RESPONSE = State()


# ===========================
# Handler principal: /roubar
# ===========================
@router.message(Command(commands=["roubar", "r"]))
async def roubar_command(message: types.Message, state: FSMContext) -> None:
    """
    Inicia o fluxo de troca de cartas entre dois usuários.

    Sintaxe esperada (exemplo):
      /roubar @usuario_alvo 20 2, 25 1 | 10 3, 42 2
      ou
      /roubar @usuario_alvo 20 2, 25 1 x 10 3, 42 2

    A parte antes do delimitador (| ou x) são as cartas que o solicitante deseja do alvo,
    e a parte após são as cartas oferecidas em troca.

    Somente o alvo poderá aceitar ou recusar a troca clicando nos botões "Aceitar" ou "Recusar".
    """

    requester_id = message.from_user.id
    text_parts = message.text.strip().split(maxsplit=1)
    if len(text_parts) < 2:
        await message.reply(
            "❗ **Uso incorreto:**\n"
            "Exemplo: `/roubar @Fulano 20 2, 25 1 | 10 3, 42 2`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    remainder_list = text_parts[1].split()
    if not remainder_list:
        await message.reply("❗ **Erro:** Argumentos insuficientes.", parse_mode=ParseMode.MARKDOWN)
        return

    # Primeiro token (possível @username)
    possible_mention = remainder_list[0]
    target_mention = None
    if possible_mention.startswith("@"):
        target_mention = possible_mention
        remainder_list = remainder_list[1:]
    else:
        # Se não tiver menção explícita, tenta extrair do reply
        if message.reply_to_message and message.reply_to_message.from_user:
            target_mention = "@" + (message.reply_to_message.from_user.username or "")
        else:
            await message.reply(
                "❗ **Erro:** Forneça @username do alvo ou responda a mensagem dele.\n"
                "Ex: `/roubar @user 20 2, 25 1 | 10 3, 42 2`",
                parse_mode=ParseMode.MARKDOWN
            )
            return

    if not remainder_list:
        await message.reply(
            "❗ **Erro:** Faltam as cartas.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    all_cards_str = " ".join(remainder_list)

    # Permitimos delimitador '|' ou 'x'
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
            "❗ **Erro:** Formato inválido. Use '|' ou 'x' p/ separar o que deseja e o que oferece.\n"
            "Ex: `/roubar @Fulano 20 2, 25 1 | 10 3, 42 2`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    left_part = all_cards_str[:delim_pos].strip()
    right_part = all_cards_str[delim_pos+1:].strip()

    if not left_part or not right_part:
        await message.reply(
            "❗ **Erro:** Partes vazias antes/depois do delimitador.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Faz parse das cartas
    try:
        requested_cards = parse_card_data(left_part)
        offered_cards = parse_card_data(right_part)
    except ValueError as ve:
        await message.reply(
            f"❗ **Erro de Formato:** {ve}",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Buscar user alvo no DB
    async with get_session() as session:
        target_user = await find_user_by_mention(session, target_mention)
        if not target_user:
            await message.reply(
                f"❌ **Erro:** Usuário `{target_mention}` não encontrado.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        target_id = target_user.id

    # Monta texto de solicitação, incluindo NOME e RARIDADE
    request_text = await build_trade_text(requested_cards, offered_cards)

    confirm_text = (
        f"🔁 **Pedido de troca:**\n\n"
        f"👤 Solicitante: {message.from_user.username or requester_id}\n"
        f"🎯 Alvo: {target_mention}\n\n"
        f"{request_text}\n"
        "Clique em **Aceitar** para confirmar ou **Recusar** para cancelar."
    )

    # Usamos callback_data com message_id
    accept_callback = f"roubar_accept:{message.message_id}"
    reject_callback = f"roubar_reject:{message.message_id}"

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Aceitar", callback_data=accept_callback),
                InlineKeyboardButton(text="❌ Recusar", callback_data=reject_callback)
            ]
        ]
    )

    sent_message = await message.reply(
        confirm_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb
    )

    # Armazena os dados da troca usando o message_id como chave
    pending_trades[sent_message.message_id] = {
        "requester_id": requester_id,
        "target_id": target_id,
        "requested_cards": requested_cards,
        "offered_cards": offered_cards
    }

    # Auto-limpeza após 3 minutos
    async def auto_cleanup():
        await asyncio.sleep(180)
        if sent_message.message_id in pending_trades:
            del pending_trades[sent_message.message_id]
            try:
                await message.reply(
                    "⌛ A proposta de troca expirou após 3 minutos sem resposta.",
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception:
                pass

    asyncio.create_task(auto_cleanup())


# ===============================
# Handler para ACEITAR a troca
# ===============================
@router.callback_query(F.data.startswith("roubar_accept:"))
async def roubar_accept_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """
    Captura o clique em 'Aceitar' e realiza a troca.
    Ex: callback_data == "roubar_accept:{message_id}"
    """

    data_parts = callback.data.split(":")
    if len(data_parts) != 2:
        await callback.answer("Dados de troca inválidos.", show_alert=True)
        return

    _, str_message_id = data_parts
    try:
        message_id = int(str_message_id)
    except ValueError:
        await callback.answer("Erro ao interpretar ID da mensagem.", show_alert=True)
        return

    # Recupera os dados da troca
    trade_data = pending_trades.get(message_id)
    if not trade_data:
        await callback.answer("Troca expirada ou inválida.", show_alert=True)
        return

    req_id = trade_data["requester_id"]
    tgt_id = trade_data["target_id"]
    requested_cards = trade_data["requested_cards"]
    offered_cards = trade_data["offered_cards"]

    # Verifica se o usuário é o alvo
    if callback.from_user.id != tgt_id:
        await callback.answer("Você não pode interagir com essa troca.", show_alert=True)
        return

    # Lógica de verificação e troca
    async with get_session() as session:
        req_query = await session.execute(
            select(User).where(User.id == req_id).options(joinedload(User.inventory))
        )
        requester = req_query.unique().scalar_one_or_none()

        tgt_query = await session.execute(
            select(User).where(User.id == tgt_id).options(joinedload(User.inventory))
        )
        target_user = tgt_query.unique().scalar_one_or_none()

        if not requester or not target_user:
            await callback.answer("Usuário não encontrado ou não registrado.", show_alert=True)
            return

        for (card_id, qty) in requested_cards:
            t_item = next((inv for inv in target_user.inventory if inv.card_id == card_id), None)
            if not t_item or t_item.quantity < qty:
                await callback.answer(
                    f"Você não possui {qty}x do card ID {card_id}.",
                    show_alert=True
                )
                return

        for (card_id, qty) in offered_cards:
            r_item = next((inv for inv in requester.inventory if inv.card_id == card_id), None)
            if not r_item or r_item.quantity < qty:
                await callback.answer(
                    f"O solicitante não possui {qty}x do card ID {card_id}.",
                    show_alert=True
                )
                return

        for (card_id, qty) in requested_cards:
            t_item = next(inv for inv in target_user.inventory if inv.card_id == card_id)
            t_item.quantity -= qty
            r_item = next((inv for inv in requester.inventory if inv.card_id == card_id), None)
            if r_item:
                r_item.quantity += qty
            else:
                session.add(Inventory(user_id=req_id, card_id=card_id, quantity=qty))

        for (card_id, qty) in offered_cards:
            r_item = next(inv for inv in requester.inventory if inv.card_id == card_id)
            r_item.quantity -= qty
            t_item = next((inv for inv in target_user.inventory if inv.card_id == card_id), None)
            if t_item:
                t_item.quantity += qty
            else:
                session.add(Inventory(user_id=tgt_id, card_id=card_id, quantity=qty))

        await session.commit()

    await callback.message.edit_text("✅ **Troca concluída com sucesso!**", parse_mode=ParseMode.MARKDOWN)
    await callback.answer("Troca finalizada!", show_alert=True)
    del pending_trades[message_id]  # Limpa a troca


# ===============================
# Handler para RECUSAR a troca
# ===============================
@router.callback_query(F.data.startswith("roubar_reject:"))
async def roubar_reject_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """
    Captura o clique em 'Recusar'.
    Ex: callback_data == "roubar_reject:{message_id}"
    """

    data_parts = callback.data.split(":")
    if len(data_parts) != 2:
        await callback.answer("Dados de troca inválidos.", show_alert=True)
        return

    _, str_message_id = data_parts
    try:
        message_id = int(str_message_id)
    except ValueError:
        await callback.answer("Erro ao interpretar ID da mensagem.", show_alert=True)
        return

    trade_data = pending_trades.get(message_id)
    if not trade_data:
        await callback.answer("Troca expirada ou inválida.", show_alert=True)
        return

    tgt_id = trade_data["target_id"]

    if callback.from_user.id != tgt_id:
        await callback.answer("Você não pode interagir com essa troca.", show_alert=True)
        return

    await callback.message.edit_text("❌ **Troca recusada.**", parse_mode=ParseMode.MARKDOWN)
    await callback.answer("Troca recusada.", show_alert=True)
    del pending_trades[message_id]  # Limpa a troca


# =========================================================
# Funções auxiliares
# =========================================================

async def build_trade_text(
    requested_cards: list[tuple[int,int]],
    offered_cards: list[tuple[int,int]]
) -> str:
    """
    Constrói a string de exibição do pedido de troca,
    incluindo ID, raridade e nome das cartas.

    A Tabela 'cards' possui: id, name, rarity, image_file_id, group_id
    """

    # Coletar todos IDs
    all_ids = {cid for (cid, _) in requested_cards} | {cid for (cid, _) in offered_cards}
    if not all_ids:
        return "Nenhuma carta listada."

    # Carrega do banco
    async with get_session() as session:
        stmt = select(Card).where(Card.id.in_(all_ids))
        res = await session.execute(stmt)
        card_objs = res.scalars().all()

    # Mapeia card_id -> (nome, raridade)
    card_map = {}
    for c in card_objs:
        card_map[c.id] = (c.name, c.rarity)

    # Monta sub-blocos
    requested_lines = []
    for cid, qty in requested_cards:
        nm, rt = card_map.get(cid, ("??", "??"))
        requested_lines.append(f"- {cid}. {rt}{nm} ({qty}x)")

    offered_lines = []
    for cid, qty in offered_cards:
        nm, rt = card_map.get(cid, ("??", "??"))
        offered_lines.append(f"- {cid}. {rt}{nm} ({qty}x)")

    text = (
        "✨ **Cartas desejadas:**\n" + "\n".join(requested_lines) + "\n\n"
        "🎁 **Cartas ofertadas:**\n" + "\n".join(offered_lines) + "\n"
    )
    return text


def parse_card_data(card_block: str) -> list[tuple[int, int]]:
    """
    Agora o usuário informa as cartas no formato:
        card_id quantity, card_id quantity
    separadas por vírgulas.

    Ex: "20 2, 25 1" => [(20,2), (25,1)]
    """
    pairs = card_block.split(",")
    cards = []
    for chunk in pairs:
        chunk = chunk.strip()
        if not chunk:
            continue
        tokens = chunk.split()
        if len(tokens) != 2:
            raise ValueError(
                f"Bloco inválido: '{chunk}'. Use 'ID QTD' e separe com vírgulas. Ex: '20 2, 25 1'."
            )
        try:
            cid_str, qty_str = tokens
            cid = int(cid_str)
            qty = int(qty_str)
            if qty <= 0:
                raise ValueError(f"Quantidade inválida '{chunk}' (deve ser > 0).")
            cards.append((cid, qty))
        except ValueError as e:
            raise ValueError(f"Erro ao interpretar '{chunk}': {e}")
    return cards


async def find_user_by_mention(session, mention: str) -> User | None:
    """
    Tenta achar um usuário cujo username ou nickname case-insensitive combine com 'mention'.
    Ex: se mention='@Fulano', limpamos '@' e comparamos com .username e .nickname (lower).
    """
    mention_clean = mention.lstrip("@").lower()
    stmt = select(User).where(
        (User.username == mention_clean)
        | (User.nickname.ilike(f"%{mention_clean}%"))
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()