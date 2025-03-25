import asyncio
from database.models import Base
from database.session import engine

async def recreate_database():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)    # Drops old tables
        await conn.run_sync(Base.metadata.create_all)  # Creates new ones with all columns

if __name__ == "__main__":
    asyncio.run(recreate_database())
