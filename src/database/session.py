from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config import settings


_is_sqlite = settings.database_url.startswith("sqlite")
engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=not _is_sqlite,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session
