from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def create_engine(database_url: str) -> AsyncEngine:
    # pool_pre_ping replaces connections the database closed (e.g. after a restart).
    return create_async_engine(database_url, pool_pre_ping=True)
