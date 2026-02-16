from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import text
from config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=True,
    future=True
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

Base = declarative_base()


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def _run_migrations(conn):
    """Lightweight schema migrations for columns added after initial create_all."""
    # Add local_path to photos table if it doesn't exist
    try:
        await conn.execute(text("SELECT local_path FROM photos LIMIT 1"))
    except Exception:
        await conn.execute(text("ALTER TABLE photos ADD COLUMN local_path VARCHAR"))


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _run_migrations(conn)
