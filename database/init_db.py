# database/init_db.py
import asyncio
from database.models import Base
from database.session import engine

async def recreate_database():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Database schema dropped and recreated.")

if __name__ == "__main__":
    asyncio.run(recreate_database())
