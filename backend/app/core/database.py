from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings


def _build_async_url(url: str) -> str:
    # asyncpg doesn't accept sslmode= as a query param — strip it and pass ssl via connect_args
    return url.replace("?sslmode=require", "").replace("&sslmode=require", "")


_db_url = _build_async_url(settings.database_url)
_ssl_required = "sslmode=require" in settings.database_url

engine = create_async_engine(
    _db_url,
    echo=settings.environment == "development",
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    connect_args={"ssl": "require"} if _ssl_required else {},
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    # Import all models so their tables are registered in Base.metadata
    import app.models.trading  # noqa: F401
    import app.models.users    # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
