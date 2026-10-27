import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from blueprint_mcp.principal import resolve_principal

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://blueprint:blueprint_dev@localhost:5433/blueprint",
)


@dataclass
class AppState:
    engine: AsyncEngine


@asynccontextmanager
async def lifespan(server: MCPServer) -> AsyncIterator[AppState]:
    engine = create_async_engine(DATABASE_URL, pool_size=5)
    try:
        yield AppState(engine=engine)
    finally:
        await engine.dispose()


mcp = MCPServer("blueprint-mcp", lifespan=lifespan)


class DocumentHit(BaseModel):
    document_id: str
    title: str
    kind: str
    project_id: str
    latest_rev: str
    latest_status: str


class RevisionInfo(BaseModel):
    rev: str
    status: str
    file_path: str
    created_at: datetime
    approved_at: datetime | None = None
    approved_by: str | None = None


class DocumentMetadata(BaseModel):
    document_id: str
    title: str
    kind: str
    project_id: str
    project_name: str
    latest_rev: str
    latest_status: str
    revisions: list[RevisionInfo]


class SearchResult(BaseModel):
    items: list[DocumentHit]
    limit: int
    offset: int
    has_more: bool


SEARCH_SQL = text("""
    SELECT d.id, d.title, d.kind, d.project_id, lr.rev, lr.status
    FROM documents d
    JOIN LATERAL (
        SELECT r.rev, r.status
        FROM revisions r
        WHERE r.tenant_id = d.tenant_id
          AND r.document_id = d.id
          AND r.status = ANY(:statuses)
        ORDER BY r.created_at DESC
        LIMIT 1
    ) lr ON true
    WHERE d.tenant_id = :tenant_id
      AND d.title ILIKE :pattern ESCAPE '\\'
      AND (CAST(:kind AS text) IS NULL OR d.kind = :kind)
    ORDER BY d.title, d.id
    LIMIT :limit OFFSET :offset
""")


def _like_pattern(query: str) -> str:
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


@mcp.tool()
async def search_documents(
    query: str,
    ctx: Context,
    kind: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> SearchResult:
    """Search engineering documents by title. Optional kind filter:
    'drawing', 'inspection_report' or 'specification'."""
    limit = max(1, min(limit, 50))
    offset = max(0, offset)
    engine = ctx.request_context.lifespan_context.engine
    principal = await resolve_principal(engine)

    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                SEARCH_SQL,
                {
                    "tenant_id": principal.tenant_id,
                    "statuses": principal.visible_statuses(),
                    "pattern": _like_pattern(query),
                    "kind": kind,
                    "limit": limit + 1,
                    "offset": offset,
                },
            )
        ).all()

    items = [
        DocumentHit(
            document_id=str(r.id),
            title=r.title,
            kind=r.kind,
            project_id=str(r.project_id),
            latest_rev=r.rev,
            latest_status=r.status,
        )
        for r in rows[:limit]
    ]
    return SearchResult(
        items=items, limit=limit, offset=offset, has_more=len(rows) > limit
    )


DOCUMENT_METADATA_SQL = text("""
    SELECT d.id, d.title, d.kind, d.project_id, p.name AS project_name
    FROM documents d
    JOIN projects p ON p.id = d.project_id AND p.tenant_id = d.tenant_id
    WHERE d.tenant_id = :tenant_id
      AND d.id = :document_id
""")

DOCUMENT_REVISIONS_SQL = text("""
    SELECT r.rev, r.status, r.file_path, r.created_at, r.approved_at, r.approved_by
    FROM revisions r
    WHERE r.tenant_id = :tenant_id
      AND r.document_id = :document_id
      AND r.status = ANY(:statuses)
    ORDER BY r.created_at DESC
""")


@mcp.tool()
async def get_document_metadata(
    document_id: str,
    ctx: Context,
) -> DocumentMetadata:
    """Get detailed metadata for an engineering document including all visible revisions."""
    try:
        doc_uuid = UUID(document_id.strip())
    except (ValueError, AttributeError):
        raise ToolError(f"Document not found: {document_id}")

    engine = ctx.request_context.lifespan_context.engine
    principal = await resolve_principal(engine)

    async with engine.connect() as conn:
        doc = (
            await conn.execute(
                DOCUMENT_METADATA_SQL,
                {"tenant_id": principal.tenant_id, "document_id": doc_uuid},
            )
        ).first()

        if doc is None:
            raise ToolError(f"Document not found: {document_id}")

        rev_rows = (
            await conn.execute(
                DOCUMENT_REVISIONS_SQL,
                {
                    "tenant_id": principal.tenant_id,
                    "document_id": doc_uuid,
                    "statuses": principal.visible_statuses(),
                },
            )
        ).all()

        if not rev_rows:
            # If no revisions are visible to this principal (e.g. a viewer querying
            # a document with only draft revisions), treat as not found to avoid
            # leaking the existence of unreleased documents.
            raise ToolError(f"Document not found: {document_id}")

    revisions = [
        RevisionInfo(
            rev=r.rev,
            status=r.status,
            file_path=r.file_path,
            created_at=r.created_at,
            approved_at=r.approved_at,
            approved_by=str(r.approved_by) if r.approved_by else None,
        )
        for r in rev_rows
    ]

    return DocumentMetadata(
        document_id=str(doc.id),
        title=doc.title,
        kind=doc.kind,
        project_id=str(doc.project_id),
        project_name=doc.project_name,
        latest_rev=revisions[0].rev,
        latest_status=revisions[0].status,
        revisions=revisions,
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")