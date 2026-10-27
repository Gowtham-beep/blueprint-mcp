import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
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


if __name__ == "__main__":
    mcp.run(transport="stdio")