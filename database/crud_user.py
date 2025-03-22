from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError
from .models import User

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
