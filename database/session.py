from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import os
from typing import AsyncGenerator, TypeVar, Callable, Any, Coroutine
from contextlib import asynccontextmanager
import logging

# Configure logger
logger = logging.getLogger(__name__)

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

# Define a TypeVar for return type
T = TypeVar('T')

async def run_transaction(
    operation: Callable[[AsyncSession], Coroutine[Any, Any, T]],
    error_msg: str = "Erro durante transação"
) -> tuple[bool, T | None, str | None]:
    """
    Executa uma operação dentro de uma transação segura, garantindo commit ou rollback.
    
    Args:
        operation: Função assíncrona que recebe uma sessão e executa operações.
        error_msg: Mensagem de erro para o log caso ocorra uma exceção.
        
    Returns:
        Tupla com (sucesso, resultado, mensagem_erro)
        - sucesso: Bool indicando se a operação foi bem-sucedida.
        - resultado: Resultado da operação ou None em caso de erro.
        - mensagem_erro: Mensagem de erro em caso de falha ou None se sucesso.
    """
    try:
        async with get_session() as session:
            async with session.begin():
                result = await operation(session)
                return True, result, None
    except Exception as e:
        logger.error(f"{error_msg}: {str(e)}", exc_info=True)
        return False, None, str(e)