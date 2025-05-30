from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload
from .models import User
from database.models import Inventory, Card

async def get_user_by_id(session, user_id):
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalars().first()

async def get_user_by_nickname(session, nickname):
    result = await session.execute(select(User).where(User.nickname == nickname))
    return result.scalars().first()

async def create_user(session, user_id, username, nickname):
    new_user = User(id=user_id, username=username, nickname=nickname)
    session.add(new_user)
    try:
        await session.commit()
        return new_user
    except IntegrityError:
        await session.rollback()
        return None

async def get_user_inventory(session, user_id):
    result = await session.execute(
        select(Inventory, Card)
        .join(Card, Inventory.card_id == Card.id)
        .where(Inventory.user_id == user_id)
        .options(joinedload(Inventory.card))  # Ensure relationships are loaded
    )
    return result.all()  # Returns a list of tuples (Inventory, Card)
