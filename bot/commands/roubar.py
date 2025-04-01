import asyncio
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from database.models import User, Inventory
from database.session import get_session

router = Router()

# ---------------------------------------------------------
# 1. Definição de estado para a troca via FSM
# ---------------------------------------------------------
class RoubarStates(StatesGroup):
    WAITING_TARGET_RESPONSE = State()

# ---------------------------------------------------------
# 2. Handler principal: /roubar
# ---------------------------------------------------------
@router.message(Command(commands=["roubar"]))
async def roubar_command(message: types.Message, state: FSMContext) -> None:
    """
    Inicia o fluxo de troca ("roubar") entre dois usuários.

    Nova sintaxe:
      /roubar @usuario_alvo <cardID quantidade, cardID quantidade> [| ou x] <cardID quantidade, cardID quantidade>

    Exemplo:
      /roubar @Fulano 20 2, 25 1 | 10 3, 42 2
    ou
      /roubar @Fulano 20 2, 25 1 x 10 3, 42 2

    A parte antes do delimitador (| ou x) são as cartas que o solicitante deseja do alvo,
    e a parte após são as cartas oferecidas em troca.

    Observação: Apenas o alvo (@Fulano) poderá confirmar ou recusar.
    """
    requester_id = message.from_user.id
    text_parts = message.text.strip().split(maxsplit=1)

    # Verifica se há algo além de "/roubar"
    if len(text_parts) < 2:
        await message.reply(
            "❗ **Uso incorreto:**\n"
            "Ex: `/roubar @Fulano 20 2, 25 1 | 10 3, 42 2`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    remainder_list = text_parts[1].strip().split()
    if not remainder_list:
        await message.reply(
            "❗ **Erro:** Argumentos insuficientes.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # 1) Identifica possivel @mention
    possible_mention = remainder_list[0]
    target_mention = None

    if possible_mention.startswith("@"):
        target_mention = possible_mention
        remainder_list = remainder_list[1:]
    else:
        # Se não tiver mention, tenta extrair do reply
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

    # Juntamos o resto
    all_cards_str = " ".join(remainder_list)

    # 2) Delimitador pode ser '|' ou 'x'
    delim_pos = None
    used_delim = None
    for delim in ("|", "x"):
        pos = all_cards_str.find(delim)
        if pos != -1:
            delim_pos = pos
            used_delim = delim
            break

    if delim_pos is None:
        # Não encontrou nem '|' nem 'x'
        await message.reply(
            "❗ **Erro:** Formato inválido. Use '|' ou 'x' para separar o que deseja e o que oferece.\n"
            "Ex: 20 2, 25 1 | 10 3, 42 2.",
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
                f"❌ **Erro:** Usuário `{target_mention}` não encontrado no BD.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        target_id = target_user.id

    # Armazena na FSM
    await state.update_data(
        requester_id=requester_id,
        target_id=target_id,
        requested_cards=requested_cards,
        offered_cards=offered_cards
    )

    # Monta texto de confirmação
    requested_text = format_card_list(requested_cards)
    offered_text = format_card_list(offered_cards)
    confirm_text = (
        f"⚠️ **Proposta de Troca**\n\n"
        f"👤 Solicitante: {message.from_user.username or requester_id}\n"
        f"🎯 Alvo: {target_mention}\n\n"
        f"**Cartas que o solicitante deseja de você:**\n{requested_text}\n\n"
        f"**Cartas oferecidas em troca:**\n{offered_text}\n\n"
        "Clique em **Aceitar** para confirmar ou **Recusar** para cancelar."
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Aceitar", callback_data="roubar_accept"),
                InlineKeyboardButton(text="❌ Recusar", callback_data="roubar_reject")
            ]
        ]
    )

    await message.reply(
        confirm_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb
    )

    await state.set_state(RoubarStates.WAITING_TARGET_RESPONSE)

    # Auto-clean: limpa o estado após 3 minutos (180s)
    async def auto_cleanup():
        await asyncio.sleep(180)
        current_state = await state.get_state()
        if current_state == RoubarStates.WAITING_TARGET_RESPONSE:
            await state.clear()
            try:
                await message.reply(
                    "⌛ A proposta de troca expirou após 3 minutos sem resposta.",
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception:
                pass

    asyncio.create_task(auto_cleanup())

# ---------------------------------------------------------
# 4. Handler para aceitar a troca
# ---------------------------------------------------------
@router.callback_query(lambda c: c.data == "roubar_accept", RoubarStates.WAITING_TARGET_RESPONSE)
async def roubar_accept_callback(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    requester_id = data.get("requester_id")
    target_id = data.get("target_id")
    requested_cards = data.get("requested_cards", [])
    offered_cards = data.get("offered_cards", [])

    # Somente o alvo pode aceitar
    if callback.from_user.id != target_id:
        await callback.answer("Você não é o alvo desta troca.", show_alert=True)
        return

    # Verificar posse e realizar troca
    async with get_session() as session:
        # Carregar user e inventário com joinedload
        requester_res = await session.execute(
            select(User).where(User.id == requester_id).options(joinedload(User.inventory))
        )
        requester = requester_res.unique().scalar_one_or_none()

        target_res = await session.execute(
            select(User).where(User.id == target_id).options(joinedload(User.inventory))
        )
        target_user = target_res.unique().scalar_one_or_none()

        if not requester or not target_user:
            await callback.answer("Erro: algum usuário não está registrado.", show_alert=True)
            return

        # Verifica se o alvo (target) tem as cartas que o solicitante está pedindo
        for (card_id, qty) in requested_cards:
            target_inv = next((inv for inv in target_user.inventory if inv.card_id == card_id), None)
            if not target_inv or target_inv.quantity < qty:
                await callback.answer(
                    f"Você não possui {qty} do card ID {card_id}.",
                    show_alert=True
                )
                return

        # Verifica se o solicitante (requester) tem as cartas oferecidas
        for (card_id, qty) in offered_cards:
            req_inv = next((inv for inv in requester.inventory if inv.card_id == card_id), None)
            if not req_inv or req_inv.quantity < qty:
                await callback.answer(
                    f"O solicitante não possui {qty} do card ID {card_id}.",
                    show_alert=True
                )
                return

        # Tudo ok, realiza a troca
        #  - target -> requester (requested_cards)
        for (card_id, qty) in requested_cards:
            target_inv = next((inv for inv in target_user.inventory if inv.card_id == card_id), None)
            if target_inv:
                target_inv.quantity -= qty
            req_inv = next((inv for inv in requester.inventory if inv.card_id == card_id), None)
            if req_inv:
                req_inv.quantity += qty
            else:
                session.add(Inventory(user_id=requester_id, card_id=card_id, quantity=qty))

        #  - requester -> target (offered_cards)
        for (card_id, qty) in offered_cards:
            req_inv = next((inv for inv in requester.inventory if inv.card_id == card_id), None)
            if req_inv:
                req_inv.quantity -= qty
            tgt_inv = next((inv for inv in target_user.inventory if inv.card_id == card_id), None)
            if tgt_inv:
                tgt_inv.quantity += qty
            else:
                session.add(Inventory(user_id=target_id, card_id=card_id, quantity=qty))

        await session.commit()

    await callback.message.edit_text(
        "✅ **Troca concluída com sucesso!**",
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer("Troca realizada com sucesso!", show_alert=True)
    await state.clear()


# ---------------------------------------------------------
# 5. Handler para recusar a troca
# ---------------------------------------------------------
@router.callback_query(lambda c: c.data == "roubar_reject", RoubarStates.WAITING_TARGET_RESPONSE)
async def roubar_reject_callback(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    target_id = data.get("target_id")

    if callback.from_user.id != target_id:
        await callback.answer("Você não é o alvo desta troca.", show_alert=True)
        return

    await callback.message.edit_text("❌ **Troca recusada.**", parse_mode=ParseMode.MARKDOWN)
    await callback.answer("Troca recusada.", show_alert=True)
    await state.clear()


# ---------------------------------------------------------
# 6. Funções auxiliares
# ---------------------------------------------------------
def parse_card_data(card_block: str) -> list[tuple[int, int]]:
    """
    Agora o usuário informa as cartas no formato:
        card_id quantity, card_id quantity, ...
    separadas por vírgulas.

    Exemplo: "20 2, 25 1, 42 5"
    => [(20,2), (25,1), (42,5)]

    Observamos que não há mais 'x' indicando quantidades.
    """
    if not card_block.strip():
        return []

    pairs = card_block.split(",")  # separa por vírgula
    cards = []
    for chunk in pairs:
        chunk = chunk.strip()
        if not chunk:
            continue
        # cada chunk deve ter 2 tokens => card_id e quantity
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
                raise ValueError(f"Quantidade inválida '{chunk}' (não pode ser <=0).")
            cards.append((cid, qty))
        except ValueError as e:
            raise ValueError(
                f"Erro ao interpretar '{chunk}': {e}"
            )
    return cards


def format_card_list(cards: list[tuple[int, int]]) -> str:
    lines = [f"- Card ID `{cid}`: `{qty}` unidades" for cid, qty in cards]
    return "\n".join(lines)


async def find_user_by_mention(session, mention: str) -> User | None:
    mention_clean = mention.lstrip("@").lower()
    user_q = await session.execute(
        select(User)
        .where((User.username == mention_clean) | (User.nickname.ilike(f"%{mention_clean}%")))
    )
    return user_q.scalar_one_or_none()
