from datetime import UTC, datetime, timedelta

import pytest

from blueprint_mcp.access import ProjectNotFound, RevisionRow, latest_approved_drawings
from blueprint_mcp.compare import diff_revisions, elapsed_days
from tests.helpers import (
    make_draft_only_doc,
    make_project,
    principal_for,
    project_id_for,
)

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 1, tzinfo=UTC)


def rev(name, status, days=0, approved_by=None, approved_at=None):
    return RevisionRow(
        rev=name,
        status=status,
        file_path="x",
        created_at=NOW + timedelta(days=days),
        approved_at=approved_at,
        approved_by=approved_by,
    )


# ---- get_latest_approved_drawings ----


async def test_latest_drawings_identical_for_engineer_and_viewer(conn):
    project = await project_id_for(conn, "Acme Steel")
    alice = await principal_for(conn, "alice@acme.test")
    vik = await principal_for(conn, "vik@acme.test")
    for_engineer = await latest_approved_drawings(conn, alice, project)
    for_viewer = await latest_approved_drawings(conn, vik, project)
    assert [(d.id, d.rev) for d in for_engineer] == [(d.id, d.rev) for d in for_viewer]
    assert [d.rev for d in for_engineer] == ["B"]  # not the newer draft C


async def test_latest_drawings_skip_other_kinds_and_drafts(conn):
    await make_draft_only_doc(
        conn, "Acme Steel"
    )  # a draft inspection report, same project
    alice = await principal_for(conn, "alice@acme.test")
    result = await latest_approved_drawings(
        conn, alice, await project_id_for(conn, "Acme Steel")
    )
    assert [d.rev for d in result] == ["B"]


async def test_latest_drawings_only_from_requested_project(conn):
    other = await make_project(conn, "Acme Steel", with_approved_drawing=True)
    alice = await principal_for(conn, "alice@acme.test")
    first = await latest_approved_drawings(
        conn, alice, await project_id_for(conn, "Acme Steel")
    )
    assert "Z drawing" not in [d.title for d in first]
    assert [d.title for d in await latest_approved_drawings(conn, alice, other)] == [
        "Z drawing"
    ]


async def test_project_without_drawings_returns_empty_list(conn):
    empty = await make_project(conn, "Acme Steel", with_approved_drawing=False)
    alice = await principal_for(conn, "alice@acme.test")
    assert await latest_approved_drawings(conn, alice, empty) == []


@pytest.mark.parametrize(
    ("user_email", "project_tenant"),
    [("bob@birla.test", "Acme Steel"), ("alice@acme.test", "Birla Fab")],
)
async def test_foreign_project_is_not_found(conn, user_email, project_tenant):
    principal = await principal_for(conn, user_email)
    with pytest.raises(ProjectNotFound):
        await latest_approved_drawings(
            conn, principal, await project_id_for(conn, project_tenant)
        )


@pytest.mark.parametrize(
    "bad_id", ["not-a-uuid", "", "00000000-0000-0000-0000-000000000000"]
)
async def test_bad_project_ids_are_not_found(conn, bad_id):
    alice = await principal_for(conn, "alice@acme.test")
    with pytest.raises(ProjectNotFound):
        await latest_approved_drawings(conn, alice, bad_id)


# ---- compare_revisions: pure functions, no database ----


def test_diff_reports_only_changed_fields():
    a = rev("A", "superseded", approved_by="u1", approved_at=NOW)
    b = rev("B", "approved", approved_by="u1", approved_at=NOW + timedelta(days=3))
    fields = {c.field: (c.from_value, c.to_value) for c in diff_revisions(a, b)}
    assert set(fields) == {"status", "approved_at"}  # approver unchanged
    assert fields["status"] == ("superseded", "approved")


def test_diff_of_identical_metadata_is_empty():
    a = rev("A", "approved", approved_by="u1", approved_at=NOW)
    b = rev("B", "approved", approved_by="u1", approved_at=NOW)
    assert diff_revisions(a, b) == []


def test_diff_never_exposes_file_path():
    a = rev("A", "draft")
    b = rev("B", "approved", approved_at=NOW)
    assert all(c.field != "file_path" for c in diff_revisions(a, b))


def test_elapsed_days():
    assert elapsed_days(rev("A", "draft", days=0), rev("B", "draft", days=2.5)) == 2.5
