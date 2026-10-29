from sqlalchemy import text

from blueprint_mcp.principal import Principal


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


async def project_id_for(conn, tenant_name: str) -> str:
    row = (
        await conn.execute(
            text("""SELECT p.id FROM projects p JOIN tenants t ON t.id = p.tenant_id
                    WHERE t.name = :n ORDER BY p.name LIMIT 1"""),
            {"n": tenant_name},
        )
    ).one()
    return str(row.id)


async def make_draft_only_doc(conn, tenant_name: str) -> str:
    row = (
        await conn.execute(
            text("""
                WITH p AS (SELECT p.id, p.tenant_id FROM projects p
                           JOIN tenants t ON t.id = p.tenant_id WHERE t.name = :n
                           ORDER BY p.name LIMIT 1),
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


async def make_project(conn, tenant_name: str, with_approved_drawing: bool) -> str:
    row = (
        await conn.execute(
            text("""INSERT INTO projects (tenant_id, name)
                    SELECT id, 'Project Z' FROM tenants WHERE name = :n
                    RETURNING id, tenant_id"""),
            {"n": tenant_name},
        )
    ).one()
    if with_approved_drawing:
        await conn.execute(
            text("""
                WITH d AS (INSERT INTO documents (tenant_id, project_id, kind, title)
                           VALUES (:t, :p, 'drawing', 'Z drawing') RETURNING id)
                INSERT INTO revisions (tenant_id, document_id, rev, status, approved_at, file_path)
                SELECT :t, id, 'A', 'approved', now(), 'docs/z.pdf' FROM d"""),
            {"t": row.tenant_id, "p": row.id},
        )
    return str(row.id)
