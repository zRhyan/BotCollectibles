import asyncio
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
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

# Removemos o global 'pending_trades'
# Agora, os dados da troca serão armazenados no FSMContext do usuário–alvo.

# ===========================
# Handler principal: /roubar
# ===========================
@router.message(Command(commands=["roubar", "r"]))
async def roubar_command(message: types.Message) -> None:
    """
    Inicia o fluxo de troca de cartas entre dois usuários.
    Lê os argumentos, faz o parse e envia a proposta de troca com teclado inline.
    Além disso, cria um FSMContext para o usuário–alvo para armazenar os dados da troca.
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

    # Extrai o @username do alvo
    possible_mention = remainder_list[0]
    target_mention = None
    if possible_mention.startswith("@"):
        target_mention = possible_mention
        remainder_list = remainder_list[1:]
    else:
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
        await message.reply("❗ **Erro:** Faltam as cartas.", parse_mode=ParseMode.MARKDOWN)
        return

    all_cards_str = " ".join(remainder_list)

    # Permite delimitadores '|' ou 'x'
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

    try:
        requested_cards = parse_card_data(left_part)
        offered_cards = parse_card_data(right_part)
    except ValueError as ve:
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

    # Cria teclado inline sem precisar de identificador na callback_data, pois o FSM estará vinculado ao alvo.
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Aceitar", callback_data="roubar_accept"),
                InlineKeyboardButton(text="❌ Recusar", callback_data="roubar_reject")
            ]
        ]
    )

    sent_message = await message.reply(
        confirm_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb
    )

    # Cria um FSMContext para o usuário–alvo (usando o chat do comando)
    target_state = FSMContext(storage=router.storage, chat_id=message.chat.id, user_id=target_id)
    # Define o estado para WAITING_TARGET_RESPONSE
    await target_state.set_state(RoubarStates.WAITING_TARGET_RESPONSE)
    # Armazena os dados da troca no FSM do alvo
    await target_state.update_data(
        trade_data={
            "requester_id": requester_id,
            "requested_cards": requested_cards,
            "offered_cards": offered_cards,
            "message_id": sent_message.message_id  # opcional para referência
        }
    )

    # Auto-limpeza: após 3 minutos, se o estado ainda estiver ativo, limpa-o e notifica.
    async def auto_cleanup():
        await asyncio.sleep(180)
        current_state = await target_state.get_state()
        if current_state == RoubarStates.WAITING_TARGET_RESPONSE:
            await target_state.clear()
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
@router.callback_query(F.data == "roubar_accept")
async def roubar_accept_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """
    Handler chamado quando o usuário–alvo clica em "Aceitar".
    Verifica se o usuário está no estado correto e, a partir dos dados armazenados,
    executa a lógica de troca.
    """
    current_state = await state.get_state()
    if current_state != RoubarStates.WAITING_TARGET_RESPONSE:
        await callback.answer("Troca expirada ou inválida.", show_alert=True)
        return

    data = await state.get_data()
    trade_data = data.get("trade_data")
    if not trade_data:
        await callback.answer("Troca expirada ou inválida.", show_alert=True)
        return

    requester_id = trade_data["requester_id"]
    requested_cards = trade_data["requested_cards"]
    offered_cards = trade_data["offered_cards"]

    async with get_session() as session:
        # Busca o solicitante com seu inventário
        req_query = await session.execute(
            select(User).where(User.id == requester_id).options(joinedload(User.inventory))
        )
        requester = req_query.unique().scalar_one_or_none()

        # Busca o usuário–alvo (quem clicou no botão)
        tgt_id = callback.from_user.id
        tgt_query = await session.execute(
            select(User).where(User.id == tgt_id).options(joinedload(User.inventory))
        )
        target_user = tgt_query.unique().scalar_one_or_none()

        if not requester or not target_user:
            await callback.answer("Usuário não encontrado ou não registrado.", show_alert=True)
            return

        # Verifica se o alvo possui os cards requisitados
        for (card_id, qty) in requested_cards:
            t_item = next((inv for inv in target_user.inventory if inv.card_id == card_id), None)
            if not t_item or t_item.quantity < qty:
                await callback.answer(
                    f"Você não possui {qty}x do card ID {card_id}.",
                    show_alert=True
                )
                return

        # Verifica se o solicitante possui os cards ofertados
        for (card_id, qty) in offered_cards:
            r_item = next((inv for inv in requester.inventory if inv.card_id == card_id), None)
            if not r_item or r_item.quantity < qty:
                await callback.answer(
                    f"O solicitante não possui {qty}x do card ID {card_id}.",
                    show_alert=True
                )
                return

        # Processa a troca: transfere os cards
        for (card_id, qty) in requested_cards:
            t_item = next(inv for inv in target_user.inventory if inv.card_id == card_id)
            t_item.quantity -= qty
            r_item = next((inv for inv in requester.inventory if inv.card_id == card_id), None)
            if r_item:
                r_item.quantity += qty
            else:
                session.add(Inventory(user_id=requester_id, card_id=card_id, quantity=qty))

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
    # Limpa o estado do usuário–alvo
    await state.clear()


# ===============================
# Handler para RECUSAR a troca
# ===============================
@router.callback_query(F.data == "roubar_reject")
async def roubar_reject_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """
    Handler chamado quando o usuário–alvo clica em "Recusar".
    Se o estado for o esperado, a troca é cancelada e o estado é limpo.
    """
    current_state = await state.get_state()
    if current_state != RoubarStates.WAITING_TARGET_RESPONSE:
        await callback.answer("Troca expirada ou inválida.", show_alert=True)
        return

    await callback.message.edit_text("❌ **Troca recusada.**", parse_mode=ParseMode.MARKDOWN)
    await callback.answer("Troca recusada.", show_alert=True)
    await state.clear()


# =========================================================
# Funções auxiliares
# =========================================================

async def build_trade_text(
    requested_cards: list[tuple[int, int]],
    offered_cards: list[tuple[int, int]]
) -> str:
    """
    Constrói a string de exibição do pedido de troca,
    incluindo ID, raridade e nome das cartas.
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
    Faz o parse das cartas informadas no formato:
        card_id quantidade, card_id quantidade
    Exemplo: "20 2, 25 1" => [(20,2), (25,1)]
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
            cid = int(tokens[0])
            qty = int(tokens[1])
            if qty <= 0:
                raise ValueError(f"Quantidade inválida '{chunk}' (deve ser > 0).")
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
        (User.username == mention_clean)
        | (User.nickname.ilike(f"%{mention_clean}%"))
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()
