import logging
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from typing import Dict, Any, Optional

from database.models import User, Inventory

logger = logging.getLogger(__name__)

async def consolidate_inventory_duplicates(session: AsyncSession, user_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Consolida entradas duplicadas do inventário para um usuário específico ou todos os usuários.
    
    Isto combina múltiplas entradas com o mesmo (user_id, card_id) em uma única entrada,
    somando suas quantidades e removendo as duplicatas.
    
    Args:
        session: Sessão SQLAlchemy ativa
        user_id: ID do usuário para consolidar, ou None para todos os usuários
    
    Returns:
        dict: Estatísticas sobre as consolidações realizadas
    """
    stats = {"users_processed": 0, "duplicates_fixed": 0, "entries_removed": 0}
    
    try:
        # Construir a consulta baseada em se temos um user_id específico ou não
        if user_id is not None:
            # Carrega o usuário específico e seu inventário
            user_query = select(User).where(User.id == user_id).options(joinedload(User.inventory))
            user_result = await session.execute(user_query)
            # Add unique() call before scalar_one_or_none() to handle joined eager loads against collections
            users = [user_result.unique().scalar_one_or_none()]
            if users[0] is None:
                logger.warning(f"Usuário ID {user_id} não encontrado para consolidação de inventário")
                return stats
        else:
            # Carrega todos os usuários e seus inventários
            user_query = select(User).options(joinedload(User.inventory))
            user_result = await session.execute(user_query)
            # Add unique() call before scalars() to handle joined eager loads against collections
            users = user_result.unique().scalars().all()
        
        # Para cada usuário, encontra duplicatas e consolida
        for user in users:
            if not user:
                continue
                
            # Agrupa entradas de inventário por card_id
            inventory_by_card = {}
            for inv in user.inventory:
                if inv.card_id not in inventory_by_card:
                    inventory_by_card[inv.card_id] = []
                inventory_by_card[inv.card_id].append(inv)
            
            # Processa cada grupo de entradas para um card_id
            user_had_duplicates = False
            for card_id, entries in inventory_by_card.items():
                if len(entries) > 1:
                    logger.info(f"Encontradas {len(entries)} duplicatas para usuário {user.id}, card {card_id}")
                    
                    # Seleciona a primeira entrada para manter (geralmente a mais antiga)
                    main_entry = entries[0]
                    total_quantity = main_entry.quantity
                    
                    # Adiciona quantidades de outras entradas à principal e marca para exclusão
                    for other_entry in entries[1:]:
                        total_quantity += other_entry.quantity
                        await session.delete(other_entry)
                        stats["entries_removed"] += 1
                    
                    # Atualiza a quantidade da entrada principal
                    main_entry.quantity = total_quantity
                    stats["duplicates_fixed"] += 1
                    user_had_duplicates = True
                    
            if user_had_duplicates:
                stats["users_processed"] += 1
        
        # Commit das alterações se houve modificações
        if stats["duplicates_fixed"] > 0:
            await session.commit()
            logger.info(f"Consolidação de inventário concluída: {stats}")
        
        return stats
        
    except Exception as e:
        logger.error(f"Erro durante consolidação de inventário: {str(e)}", exc_info=True)
        await session.rollback()
        raise
