from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from blueprint_mcp.principal import Principal


class DocumentNotFound(Exception):
    """Missing, other-tenant and not-visible documents all look the same."""


class ProjectNotFound(Exception):
    """Missing and other-tenant projects look the same."""


@dataclass(frozen=True)
class RevisionRow:
    rev: str
    status: str
    file_path: str
    created_at: datetime
    approved_at: datetime | None
    approved_by: UUID | None


@dataclass(frozen=True)
class VisibleDocument:
    id: UUID
    title: str
    kind: str
    project_id: UUID
    project_name: str
    revisions: list[RevisionRow]  # newest first, only what the principal may see


LOAD_SQL = text("""
    SELECT d.id, d.title, d.kind, d.project_id, p.name AS project_name,
           r.rev, r.status, r.file_path, r.created_at, r.approved_at, r.approved_by
    FROM documents d
    JOIN projects p  ON p.tenant_id = d.tenant_id AND p.id = d.project_id
    JOIN revisions r ON r.tenant_id = d.tenant_id AND r.document_id = d.id
    WHERE d.tenant_id = :tenant_id
      AND d.id = :document_id
      AND r.status = ANY(:statuses)
    ORDER BY r.created_at DESC, r.rev DESC
""")


async def load_visible_document(
    conn: AsyncConnection, principal: Principal, document_id: str
) -> VisibleDocument:
    try:
        doc_uuid = UUID(document_id.strip())
    except ValueError:
        raise DocumentNotFound() from None

    rows = (
        await conn.execute(
            LOAD_SQL,
            {
                "tenant_id": principal.tenant_id,
                "document_id": doc_uuid,
                "statuses": principal.visible_statuses(),
            },
        )
    ).all()

    if not rows:
        raise DocumentNotFound()

    first = rows[0]
    return VisibleDocument(
        id=first.id,
        title=first.title,
        kind=first.kind,
        project_id=first.project_id,
        project_name=first.project_name,
        revisions=[
            RevisionRow(
                r.rev, r.status, r.file_path, r.created_at, r.approved_at, r.approved_by
            )
            for r in rows
        ],
    )


@dataclass(frozen=True)
class ApprovedDrawing:
    id: UUID
    title: str
    rev: str
    approved_at: datetime | None
    approved_by: UUID | None


PROJECT_EXISTS_SQL = text(
    "SELECT 1 FROM projects WHERE tenant_id = :tenant_id AND id = :project_id"
)

LATEST_APPROVED_DRAWINGS_SQL = text("""
    SELECT * FROM (
        SELECT DISTINCT ON (d.id)
               d.id, d.title, r.rev, r.approved_at, r.approved_by
        FROM documents d
        JOIN revisions r ON r.tenant_id = d.tenant_id AND r.document_id = d.id
        WHERE d.tenant_id = :tenant_id
          AND d.project_id = :project_id
          AND d.kind = 'drawing'
          AND r.status = 'approved'
          AND r.status = ANY(:statuses)
        ORDER BY d.id, r.approved_at DESC
    ) latest
    ORDER BY title, id
""")


async def latest_approved_drawings(
    conn: AsyncConnection, principal: Principal, project_id: str
) -> list[ApprovedDrawing]:
    try:
        project_uuid = UUID(project_id.strip())
    except ValueError:
        raise ProjectNotFound() from None

    params = {"tenant_id": principal.tenant_id, "project_id": project_uuid}
    if (await conn.execute(PROJECT_EXISTS_SQL, params)).first() is None:
        raise ProjectNotFound()

    rows = (
        await conn.execute(
            LATEST_APPROVED_DRAWINGS_SQL,
            {**params, "statuses": principal.visible_statuses()},
        )
    ).all()
    return [
        ApprovedDrawing(r.id, r.title, r.rev, r.approved_at, r.approved_by)
        for r in rows
    ]
