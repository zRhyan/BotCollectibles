import asyncio
import time
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

    # Gerar um ID único para esta transação
    transaction_id = f"{requester_id}:{target_id}:{int(time.time())}"

    # Salvamos na storage global para ser acessível por ambos usuários
    # Essencial: Usamos uma chave global independente do usuário
    await state.storage.set_data(
        bot=state.bot, 
        key=f"trade:{transaction_id}",
        data={
            "requester_id": requester_id,
            "target_id": target_id,
            "requested_cards": requested_cards,
            "offered_cards": offered_cards,
            "created_at": time.time()
        }
    )

    # Monta texto de solicitação, incluindo NOME e RARIDADE
    request_text = await build_trade_text(requested_cards, offered_cards)

    confirm_text = (
        f"🔁 **Pedido de troca:**\n\n"
        f"👤 Solicitante: {message.from_user.username or requester_id}\n"
        f"🎯 Alvo: {target_mention}\n\n"
        f"{request_text}\n"
        "Clique em **Aceitar** para confirmar ou **Recusar** para cancelar."
    )

    # O transaction_id é usado no callback_data para rastrear esta troca específica
    accept_callback = f"roubar_accept:{transaction_id}"
    reject_callback = f"roubar_reject:{transaction_id}"

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Aceitar", callback_data=accept_callback),
                InlineKeyboardButton(text="❌ Recusar", callback_data=reject_callback)
            ]
        ]
    )

    sent_msg = await message.reply(
        confirm_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb
    )

    # Auto-limpeza após 3 minutos
    async def auto_cleanup():
        await asyncio.sleep(180)
        # Verificar se a transação ainda existe e não foi processada
        trade_data = await state.storage.get_data(bot=state.bot, key=f"trade:{transaction_id}")
        if trade_data:
            # Limpar dados da transação expirada
            await state.storage.set_data(bot=state.bot, key=f"trade:{transaction_id}", data={})
            try:
                await sent_msg.edit_text(
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
    Ex: callback_data == "roubar_accept:{transaction_id}"
    """
    # Extrair o ID de transação
    transaction_id = callback.data.split(":", 1)[1]
    
    # Recuperar dados da transação global
    trade_data = await state.storage.get_data(
        bot=state.bot,
        key=f"trade:{transaction_id}"
    )
    
    if not trade_data:
        await callback.answer("Esta transação expirou ou é inválida.", show_alert=True)
        return
    
    req_id = trade_data.get("requester_id")
    tgt_id = trade_data.get("target_id")
    requested_cards = trade_data.get("requested_cards", [])
    offered_cards = trade_data.get("offered_cards", [])
    
    # Check se callback.from_user.id == tgt_id
    if callback.from_user.id != tgt_id:
        await callback.answer("Você não pode interagir com essa troca.", show_alert=True)
        return

    # Lógica de verificação e troca
    async with get_session() as session:
        # Carrega info do solicitante e do alvo
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

        # Verifica se o alvo (target_user) tem as cartas => requested_cards
        for (card_id, qty) in requested_cards:
            t_item = next((inv for inv in target_user.inventory if inv.card_id == card_id), None)
            if not t_item or t_item.quantity < qty:
                await callback.answer(
                    f"Você não possui {qty}x do card ID {card_id}.",
                    show_alert=True
                )
                return

        # Verifica se o solicitante tem => offered_cards
        for (card_id, qty) in offered_cards:
            r_item = next((inv for inv in requester.inventory if inv.card_id == card_id), None)
            if not r_item or r_item.quantity < qty:
                await callback.answer(
                    f"O solicitante não possui {qty}x do card ID {card_id}.",
                    show_alert=True
                )
                return

        # Ok, efetua a troca
        # target->requester
        for (card_id, qty) in requested_cards:
            t_item = next(inv for inv in target_user.inventory if inv.card_id == card_id)
            t_item.quantity -= qty
            r_item = next((inv for inv in requester.inventory if inv.card_id == card_id), None)
            if r_item:
                r_item.quantity += qty
            else:
                session.add(Inventory(user_id=req_id, card_id=card_id, quantity=qty))

        # requester->target
        for (card_id, qty) in offered_cards:
            r_item = next(inv for inv in requester.inventory if inv.card_id == card_id)
            r_item.quantity -= qty
            t_item = next((inv for inv in target_user.inventory if inv.card_id == card_id), None)
            if t_item:
                t_item.quantity += qty
            else:
                session.add(Inventory(user_id=tgt_id, card_id=card_id, quantity=qty))

        await session.commit()

    # Limpar dados de transação
    await state.storage.set_data(bot=state.bot, key=f"trade:{transaction_id}", data={})
    
    # Edição de texto no chat
    await callback.message.edit_text("✅ **Troca concluída com sucesso!**", parse_mode=ParseMode.MARKDOWN)
    await callback.answer("Troca finalizada!", show_alert=True)


# ===============================
# Handler para RECUSAR a troca
# ===============================
@router.callback_query(F.data.startswith("roubar_reject:"))
async def roubar_reject_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """
    Captura o clique em 'Recusar'.
    Ex: callback_data == "roubar_reject:{transaction_id}"
    """
    # Extrair o ID de transação
    transaction_id = callback.data.split(":", 1)[1]
    
    # Recuperar dados da transação global
    trade_data = await state.storage.get_data(
        bot=state.bot,
        key=f"trade:{transaction_id}"
    )
    
    if not trade_data:
        await callback.answer("Esta transação expirou ou é inválida.", show_alert=True)
        return
    
    tgt_id = trade_data.get("target_id")
    
    if callback.from_user.id != tgt_id:
        await callback.answer("Você não pode interagir com essa troca.", show_alert=True)
        return

    # Limpar dados de transação
    await state.storage.set_data(bot=state.bot, key=f"trade:{transaction_id}", data={})
    
    await callback.message.edit_text("❌ **Troca recusada.**", parse_mode=ParseMode.MARKDOWN)
    await callback.answer("Troca recusada.", show_alert=True)


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