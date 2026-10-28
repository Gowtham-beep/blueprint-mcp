import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ResourceNotFoundError, ToolError
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from blueprint_mcp import prompts
from blueprint_mcp.access import DocumentNotFound, load_visible_document
from blueprint_mcp.principal import resolve_principal
from blueprint_mcp.storage import StorageError, resolve_storage_path

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
prompts.register(mcp)


class DocumentHit(BaseModel):
    document_id: str
    title: str
    kind: str
    project_id: str
    latest_rev: str
    latest_status: str


class RevisionInfo(BaseModel):
    rev: str
    uri: str
    status: str
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


@mcp.tool()
async def get_document_metadata(
    document_id: str,
    ctx: Context,
) -> DocumentMetadata:
    """Get detailed metadata for an engineering document including all visible revisions."""
    engine = ctx.request_context.lifespan_context.engine
    principal = await resolve_principal(engine)

    async with engine.connect() as conn:
        try:
            doc = await load_visible_document(conn, principal, document_id)
        except DocumentNotFound:
            raise ToolError("Document not found") from None

    revisions = [
        RevisionInfo(
            rev=r.rev,
            uri=f"blueprint://documents/{doc.id}/revisions/{r.rev}",
            status=r.status,
            created_at=r.created_at,
            approved_at=r.approved_at,
            approved_by=str(r.approved_by) if r.approved_by else None,
        )
        for r in doc.revisions
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


@mcp.resource(
    "blueprint://documents/{document_id}/revisions/{rev}",
    name="revision_file",
    description="Get the file path for a specific revision of a document.",
    mime_type="application/pdf",
)
async def read_revision_file(document_id: str, rev: str, ctx: Context) -> bytes:
    engine = ctx.request_context.lifespan_context.engine
    principal = await resolve_principal(engine)

    async with engine.connect() as conn:
        try:
            doc = await load_visible_document(conn, principal, document_id)
        except DocumentNotFound:
            raise ResourceNotFoundError("Document not found") from None

    match = next((r for r in doc.revisions if r.rev == rev), None)
    if match is None:
        raise ResourceNotFoundError("Revision not found")
    try:
        return resolve_storage_path(match.file_path).read_bytes()
    except StorageError:
        raise ResourceNotFoundError("Resource not found") from None


if __name__ == "__main__":
    mcp.run(transport="stdio")
