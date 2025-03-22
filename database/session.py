from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import os
from typing import AsyncGenerator
from contextlib import asynccontextmanager

# Load environment variables
load_dotenv()

# Load the DATABASE_URL from the environment
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set in the environment variables.")

# Debug print to verify DATABASE_URL
print(f"Loaded DATABASE_URL: {DATABASE_URL}")

# Create the async engine with asyncpg explicitly
engine = create_async_engine(DATABASE_URL, echo=False, future=True)

# Create the session factory
AsyncSessionLocal = sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)

# Dependency to get the session
@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session