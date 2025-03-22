import asyncio
import sys
import os

# Add the root directory to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.session import engine

async def test_connection():
    try:
        async with engine.connect() as conn:
            result = await conn.execute("SELECT 1")
            print("Database connection successful:", result.scalar())
    except Exception as e:
        print("Database connection failed:", str(e))

if __name__ == "__main__":
    asyncio.run(test_connection())