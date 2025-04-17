import os
import logging
import time
from dotenv import load_dotenv
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from sqlalchemy.future import select
from sqlalchemy import update, delete
from database.models import User, Card, Inventory
from database.session import get_session

# Configurar logging
logger = logging.getLogger(__name__)

# Carregar variáveis de ambiente
load_dotenv()

ALLOWED_USERNAMES = os.getenv("ALLOWED_USERNAMES", "").split(",")  # Lista de nomes de usuário permitidos

router = Router()

@router.message(Command("modcard"))
async def modify_card_quantity(message: types.Message):
    """
    Comando para modificar a quantidade de uma carta no inventário de um usuário.
    Uso: /modcard nickname cardid xquantity
    
    Exemplos:
    - /modcard joao 42 5  # Define que o usuário 'joao' terá 5 unidades da carta com ID 42
    - /modcard maria 100 0  # Remove todas as unidades da carta com ID 100 do inventário de 'maria'
    """
    user_id = message.from_user.id
    
    # Verificar se o usuário é permitido
    if message.from_user.username not in ALLOWED_USERNAMES:
        logger.warning(f"Acesso negado para usuário {message.from_user.username} - não está na lista ALLOWED_USERNAMES")
        await message.reply(
            "🚫 **Acesso negado!** Você não tem permissão para usar este comando.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Verificar se o usuário é um administrador
    try:
        async with get_session() as session:
            admin_result = await session.execute(select(User).where(User.id == user_id))
            admin_user = admin_result.scalar_one_or_none()
            
            if not admin_user:
                await message.reply(
                    "❌ **Erro:** Seu usuário não foi encontrado no banco de dados.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
                
            if admin_user.is_admin != 1:
                await message.reply(
                    "🚫 **Acesso negado!** Somente administradores podem usar este comando.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
                
            logger.debug(f"Usuário {user_id} é admin, permissão concedida")
    except Exception as e:
        logger.error(f"Erro ao verificar permissões de admin: {str(e)}", exc_info=True)
        await message.reply(
            "❌ **Erro ao verificar permissões.** Por favor, tente novamente mais tarde.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Validar argumentos do comando
    text_parts = message.text.split(maxsplit=3)
    if len(text_parts) < 4:
        await message.reply(
            "❗ **Erro:** Formato incorreto. Use `/modcard nickname cardid xquantity`\n\n"
            "**Exemplos:**\n"
            "- `/modcard joao 42 5` - Define 5 unidades da carta 42 para o usuário 'joao'\n"
            "- `/modcard maria 100 0` - Remove todas as unidades da carta 100 do usuário 'maria'",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Extrair os argumentos
    nickname = text_parts[1].strip()
    
    try:
        card_id = int(text_parts[2].strip())
    except ValueError:
        await message.reply(
            "❗ **Erro:** O ID da carta deve ser um número inteiro.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    try:
        quantity = int(text_parts[3].strip())
        if quantity < 0:
            raise ValueError("A quantidade não pode ser negativa")
    except ValueError as e:
        await message.reply(
            f"❗ **Erro:** {str(e) if 'quantidade' in str(e) else 'A quantidade deve ser um número inteiro não-negativo.'}",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Processar a alteração
    try:
        async with get_session() as session:
            # Verificar se o usuário existe
            user_result = await session.execute(select(User).where(User.nickname == nickname))
            user = user_result.scalar_one_or_none()
            
            if not user:
                await message.reply(
                    f"❌ **Erro:** Usuário com nickname '{nickname}' não foi encontrado.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            
            # Verificar se a carta existe
            card_result = await session.execute(select(Card).where(Card.id == card_id))
            card = card_result.scalar_one_or_none()
            
            if not card:
                await message.reply(
                    f"❌ **Erro:** Carta com ID {card_id} não foi encontrada.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            
            # Encontrar o registro no inventário
            inventory_result = await session.execute(
                select(Inventory).where(
                    Inventory.user_id == user.id,
                    Inventory.card_id == card_id
                )
            )
            inventory_item = inventory_result.scalar_one_or_none()
            
            if quantity == 0:
                # Se a quantidade é 0, remover a carta do inventário
                if inventory_item:
                    await session.delete(inventory_item)
                    await session.commit()
                    await message.reply(
                        f"✅ **Sucesso!** Todas as unidades da carta ID {card_id} ({card.name}) foram removidas do inventário de '{nickname}'.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                else:
                    await message.reply(
                        f"ℹ️ O usuário '{nickname}' já não possui a carta ID {card_id} ({card.name}) em seu inventário.",
                        parse_mode=ParseMode.MARKDOWN
                    )
            else:
                # Se a quantidade é maior que 0
                if inventory_item:
                    # Se o item já existe, atualizar a quantidade
                    old_quantity = inventory_item.quantity
                    inventory_item.quantity = quantity
                    await session.commit()
                    await message.reply(
                        f"✅ **Sucesso!** A quantidade da carta ID {card_id} ({card.name}) para '{nickname}' foi alterada de {old_quantity} para {quantity}.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                else:
                    # Se o item não existe, criar um novo
                    new_inventory = Inventory(user_id=user.id, card_id=card_id, quantity=quantity)
                    session.add(new_inventory)
                    await session.commit()
                    await message.reply(
                        f"✅ **Sucesso!** Adicionadas {quantity} unidades da carta ID {card_id} ({card.name}) ao inventário de '{nickname}'.",
                        parse_mode=ParseMode.MARKDOWN
                    )
            
            # Log da alteração
            logger.info(
                f"Admin {message.from_user.username or message.from_user.id} modificou a carta {card_id} ({card.name}) "
                f"do usuário {nickname} para {quantity} unidades"
            )
            
    except Exception as e:
        logger.error(f"Erro ao modificar quantidade de carta: {str(e)}", exc_info=True)
        await message.reply(
            f"❌ **Erro ao processar a solicitação:** {str(e)}",
            parse_mode=ParseMode.MARKDOWN
        )