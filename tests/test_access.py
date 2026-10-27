import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from blueprint_mcp.access import DocumentNotFound, load_visible_document
from blueprint_mcp.principal import Principal
from blueprint_mcp.server import DATABASE_URL

pytestmark = pytest.mark.anyio


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


async def principal_for(conn, email: str) -> Principal:
    row = (
        await conn.execute(
            text("SELECT id, tenant_id, role FROM users WHERE email = :e"), {"e": email}
        )
    ).one()
    return Principal(user_id=row.id, tenant_id=row.tenant_id, role=row.role)


async def drawing_id(conn, tenant_name: str) -> str:
    row = (
        await conn.execute(
            text("""SELECT d.id FROM documents d JOIN tenants t ON t.id = d.tenant_id
                    WHERE t.name = :n AND d.kind = 'drawing'"""),
            {"n": tenant_name},
        )
    ).one()
    return str(row.id)


async def make_draft_only_doc(conn, tenant_name: str) -> str:
    row = (
        await conn.execute(
            text("""
                WITH p AS (SELECT p.id, p.tenant_id FROM projects p
                           JOIN tenants t ON t.id = p.tenant_id WHERE t.name = :n),
                d AS (INSERT INTO documents (tenant_id, project_id, kind, title)
                      SELECT tenant_id, id, 'inspection_report', 'Draft only' FROM p
                      RETURNING id, tenant_id)
                INSERT INTO revisions (tenant_id, document_id, rev, status, file_path)
                SELECT tenant_id, id, 'A', 'draft', 'docs/x.pdf' FROM d
                RETURNING document_id"""),
            {"n": tenant_name},
        )
    ).one()
    return str(row.document_id)


async def test_engineer_sees_all_revisions(conn):
    p = await principal_for(conn, "alice@acme.test")
    doc = await load_visible_document(conn, p, await drawing_id(conn, "Acme Steel"))
    assert [r.rev for r in doc.revisions] == ["C", "B", "A"]


async def test_viewer_sees_only_approved(conn):
    p = await principal_for(conn, "vik@acme.test")
    doc = await load_visible_document(conn, p, await drawing_id(conn, "Acme Steel"))
    assert [r.rev for r in doc.revisions] == ["B"]


async def test_cross_tenant_is_not_found(conn):
    bob = await principal_for(conn, "bob@birla.test")
    with pytest.raises(DocumentNotFound):
        await load_visible_document(conn, bob, await drawing_id(conn, "Acme Steel"))


async def test_viewer_cannot_see_draft_only_document(conn):
    vik = await principal_for(conn, "vik@acme.test")
    with pytest.raises(DocumentNotFound):
        await load_visible_document(conn, vik, await make_draft_only_doc(conn, "Acme Steel"))


@pytest.mark.parametrize("bad_id", ["not-a-uuid", "", "00000000-0000-0000-0000-000000000000"])
async def test_bad_ids_are_not_found(conn, bad_id):
    alice = await principal_for(conn, "alice@acme.test")
    with pytest.raises(DocumentNotFound):
        await load_visible_document(conn, alice, bad_id)