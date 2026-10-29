import pytest

from blueprint_mcp.access import DocumentNotFound, load_visible_document
from tests.helpers import drawing_id, make_draft_only_doc, principal_for

pytestmark = pytest.mark.anyio


async def test_engineer_sees_all_revisions(conn):
    p = await principal_for(conn, "alice@acme.test")
    doc = await load_visible_document(conn, p, await drawing_id(conn, "Acme Steel"))
    assert [r.rev for r in doc.revisions] == ["C", "B", "A"]


async def test_viewer_sees_only_approved(conn):
    p = await principal_for(conn, "vik@acme.test")
    doc = await load_visible_document(conn, p, await drawing_id(conn, "Acme Steel"))
    assert [r.rev for r in doc.revisions] == ["B"]


async def test_viewer_cannot_see_draft_only_document(conn):
    vik = await principal_for(conn, "vik@acme.test")
    with pytest.raises(DocumentNotFound):
        await load_visible_document(conn, vik, await make_draft_only_doc(conn, "Acme Steel"))


@pytest.mark.parametrize("bad_id", ["not-a-uuid", "", "00000000-0000-0000-0000-000000000000"])
async def test_bad_ids_are_not_found(conn, bad_id):
    alice = await principal_for(conn, "alice@acme.test")
    with pytest.raises(DocumentNotFound):
        await load_visible_document(conn, alice, bad_id)


async def test_birla_engineer_sees_own_revisions(conn):
    bob = await principal_for(conn, "bob@birla.test")
    doc = await load_visible_document(conn, bob, await drawing_id(conn, "Birla Fab"))
    assert [r.rev for r in doc.revisions] == ["C", "B", "A"]


@pytest.mark.parametrize(
    ("user_email", "foreign_tenant"),
    [
        ("bob@birla.test", "Acme Steel"),
        ("alice@acme.test", "Birla Fab"),
        ("vik@acme.test", "Birla Fab"),
    ],
)
async def test_cross_tenant_rejection_matrix(conn, user_email, foreign_tenant):
    principal = await principal_for(conn, user_email)
    foreign_doc_id = await drawing_id(conn, foreign_tenant)
    with pytest.raises(DocumentNotFound):
        await load_visible_document(conn, principal, foreign_doc_id)


async def test_cross_tenant_cannot_see_draft_only_document(conn):
    bob = await principal_for(conn, "bob@birla.test")
    acme_draft_id = await make_draft_only_doc(conn, "Acme Steel")
    with pytest.raises(DocumentNotFound):
        await load_visible_document(conn, bob, acme_draft_id)