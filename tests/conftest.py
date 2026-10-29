import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from blueprint_mcp.server import DATABASE_URL


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def conn():
    engine = create_async_engine(DATABASE_URL)
    async with engine.connect() as c:
        trans = await c.begin()
        yield c
        await trans.rollback()  # every test's writes vanish
    await engine.dispose()