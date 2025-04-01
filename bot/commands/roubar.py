"""
Roubar Command (Aiogram v3)
===========================
Este comando /roubar permite que um usuário (chamado aqui de “solicitante”) peça determinadas cartas que outro usuário
(possível “alvo”) possui, oferecendo em troca outras cartas. Somente o “alvo” (usuário mencionado) poderá confirmar ou recusar.

Sintaxe de uso (exemplo):
    /roubar @usuario_destino  20 x2 25 x1 | 10 x3 42 x2

Significa:
- O solicitante quer "pegar" do usuário destino as cartas:
    ID=20 (2 unidades), ID=25 (1 unidade)
- E está oferecendo em troca suas próprias cartas:
    ID=10 (3 unidades), ID=42 (2 unidades)
    
O bot então envia uma mensagem para o grupo, com dois botões inline: "Aceitar" e "Recusar".
Apenas o usuário alvo (@usuario_destino) pode interagir com esses botões.
Quando clica em "Aceitar", o bot verifica se ambos de fato possuem as quantidades necessárias,
e caso sim, efetua a troca e envia uma notificação de sucesso.
"""

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
    Inicia o fluxo de troca ("roubar").

    Sintaxe esperada (exemplo):
        /roubar @usuario_destino  20 x2 25 x1 | 10 x3 42 x2

    - O trecho antes do '|' representa as cartas que o solicitante quer pegar do alvo.
    - O trecho depois do '|' representa as cartas que o solicitante está oferecendo ao alvo.
    - Se o usuário mencionar o alvo respondendo a mensagem dele no grupo, isso também é válido
      (porém, iremos priorizar o @username se fornecido explicitamente).

    Observação: Ao final, apenas o usuário alvo poderá aceitar ou recusar a proposta.
    """
    requester_id = message.from_user.id
    text_parts = message.text.strip().split(maxsplit=1)

    # Verifica se há algo além de "/roubar"
    if len(text_parts) < 2:
        await message.reply(
            "❗ **Uso incorreto:**\n"
            "Ex: `/roubar @usuario_destino 20 x2 25 x1 | 10 x3 42 x1`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Primeiro token após /roubar (possível @username, ou parte de cartas)
    remainder = text_parts[1].strip().split()
    if not remainder:
        await message.reply(
            "❗ **Erro:** Argumentos insuficientes.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Pode ser que o primeiro token seja "@username" ou "apenas" parte do card list
    possible_username = remainder[0]
    target_mention = None
    # Verifica se começa com "@"
    if possible_username.startswith("@"):
        target_mention = possible_username
        # Remove esse token e deixa o resto no 'all_cards_part'
        remainder = remainder[1:]
    else:
        # Tentar extrair do reply se existir
        if message.reply_to_message and message.reply_to_message.from_user:
            target_mention = "@" + (message.reply_to_message.from_user.username or "")
        else:
            # Falta menção
            await message.reply(
                "❗ **Erro:** Forneça o @username do alvo ou responda a mensagem dele no grupo.\n"
                "Ex: `/roubar @usuario_destino 20 x2 | 10 x1`",
                parse_mode=ParseMode.MARKDOWN
            )
            return

    # Se remainder vazio => erro
    if not remainder:
        await message.reply(
            "❗ **Erro:** Faltam as cartas.\n"
            "Use `/roubar @usuario 10 x2 | 42 x1` etc.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    all_cards_str = " ".join(remainder).strip()

    # Procuramos o caractere '|'
    if "|" not in all_cards_str:
        await message.reply(
            "❗ **Erro:** Formato inválido. Falta o `|` separando cartas que você deseja e as que oferece.\n"
            "Exemplo: `/roubar @user 20 x2 | 25 x1`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    requested_str, offered_str = all_cards_str.split("|", maxsplit=1)
    requested_str = requested_str.strip()
    offered_str = offered_str.strip()

    if not requested_str or not offered_str:
        await message.reply(
            "❗ **Erro:** Formato inválido. As duas partes (antes e depois do `|`) devem conter cartas.\n"
            "Exemplo: `/roubar @user 20 x2 21 x1 | 25 x2`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Fazemos parse do requested e do offered
    try:
        requested_cards = parse_card_data(requested_str)
        offered_cards = parse_card_data(offered_str)
    except ValueError as ve:
        await message.reply(
            f"❗ **Erro de Formato:** {ve}",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # 3. Buscar o user alvo do DB via mention (ou fallback se não achar)
    #    Se o mention estiver vazio, poderia ser no reply ou nickname no DB etc.
    async with get_session() as session:
        target_user = await find_user_by_mention(session, target_mention)
        if not target_user:
            await message.reply(
                f"❌ **Erro:** Não encontrei nenhum usuário com username ou nickname `{target_mention}`.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

    target_id = target_user.id

    # Armazena na FSM
    await state.update_data(
        requester_id=requester_id,
        target_id=target_id,
        requested_cards=requested_cards,  # que o requester quer "pegar"
        offered_cards=offered_cards       # que o requester oferece em troca
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

    # Inline buttons
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
        state_data = await state.get_data()
        # Checa se o estado ainda é o esperado antes de limpar
        current_state = await state.get_state()
        if current_state == RoubarStates.WAITING_TARGET_RESPONSE:
            await state.clear()
            try:
                await message.reply(
                    "⌛ A proposta de troca expirou após 3 minutos sem resposta.",
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception:
                pass  # o chat pode ter sido removido ou a mensagem não ser mais acessível

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
                    f"Você não possui {qty}x do card ID {card_id}.",
                    show_alert=True
                )
                return

        # Verifica se o solicitante (requester) tem as cartas oferecidas
        for (card_id, qty) in offered_cards:
            req_inv = next((inv for inv in requester.inventory if inv.card_id == card_id), None)
            if not req_inv or req_inv.quantity < qty:
                await callback.answer(
                    f"O solicitante não possui {qty}x do card ID {card_id}.",
                    show_alert=True
                )
                return

        # Tudo ok, realiza a troca
        #  - target -> requester (requested_cards)
        for (card_id, qty) in requested_cards:
            target_inv = next((inv for inv in target_user.inventory if inv.card_id == card_id), None)
            if target_inv:  # safe
                target_inv.quantity -= qty
            # Adicionar ao requester
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
            # Adicionar ao target
            tgt_inv = next((inv for inv in target_user.inventory if inv.card_id == card_id), None)
            if tgt_inv:
                tgt_inv.quantity += qty
            else:
                session.add(Inventory(user_id=target_id, card_id=card_id, quantity=qty))

        await session.commit()

    # Se chegou até aqui, troca concluída
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

    # Somente o alvo pode recusar
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
    Recebe algo como "20 x2 25 x1" e devolve [(20,2), (25,1)].
    Utiliza espaço para separar blocos e "x" para separar ID e quantidade.
    """
    tokens = card_block.split()
    if not tokens or len(tokens) % 2 != 0:
        raise ValueError(
            f"Formato inválido para blocos de cartas: '{card_block}'. "
            "Exemplo correto: '20 x2 25 x1'."
        )

    cards = []
    for i in range(0, len(tokens), 2):
        card_str = tokens[i]
        qty_str = tokens[i+1]

        # Esperamos "x2" no qty_str => remover 'x'
        if not qty_str.startswith("x"):
            raise ValueError(
                f"Formato inválido em '{tokens[i]} {tokens[i+1]}'. Esperado algo como '20 x2'."
            )
        try:
            card_id = int(card_str)
            qty = int(qty_str[1:])  # remove o 'x'
            if qty <= 0:
                raise ValueError(f"Quantidade inválida em '{tokens[i]} {tokens[i+1]}' (não pode ser <= 0).")
            cards.append((card_id, qty))
        except ValueError:
            raise ValueError(f"Erro ao interpretar '{tokens[i]} {tokens[i+1]}'. Exemplo correto: '20 x2'.")

    return cards


def format_card_list(cards: list[tuple[int, int]]) -> str:
    """
    Retorna string para exibir, ex:
    - Card ID `20`: `2` unidades
    - Card ID `25`: `1` unidades
    """
    lines = []
    for cid, qty in cards:
        lines.append(f"- Card ID `{cid}`: `{qty}` unidades")
    return "\n".join(lines)


async def find_user_by_mention(session, mention: str) -> User | None:
    """
    Tenta encontrar um usuário no BD usando:
      1) mention sem '@' => se for nickname
      2) mention com '@' => se for username
    No seu BD, verifique se faz sentido:
      - Se username armazena no User.username
      - Se nickname armazena no User.nickname
    """
    mention_clean = mention.lstrip("@").lower()  # remove '@' e converte pra minúsculo
    # Tenta buscar por username
    user_q = await session.execute(
        select(User)
        .where(
            (User.username == mention_clean)
            | (User.nickname.ilike(f"%{mention_clean}%"))
        )
    )
    user_db = user_q.scalar_one_or_none()
    return user_db

