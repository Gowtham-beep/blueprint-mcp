"""Create one tiny valid PDF per revision row, at STORAGE_ROOT/<file_path>."""

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from blueprint_mcp.server import DATABASE_URL
from blueprint_mcp.storage import STORAGE_ROOT


def tiny_pdf(line: str) -> bytes:
    stream = f"BT /F1 14 Tf 40 100 Td ({line}) Tj ET".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 400 200] /Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R >> >> >>"
        ),
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for n, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % n + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objs) + 1,
        xref,
    )
    return bytes(out)


async def main() -> None:
    engine = create_async_engine(DATABASE_URL)
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT r.file_path, r.rev, d.title, t.name AS tenant "
                    "FROM revisions r JOIN documents d ON d.id = r.document_id "
                    "JOIN tenants t ON t.id = r.tenant_id"
                )
            )
        ).all()
    await engine.dispose()
    for r in rows:
        path = STORAGE_ROOT / r.file_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(tiny_pdf(f"{r.tenant} - {r.title} - revision {r.rev}"))
    print(f"wrote {len(rows)} files under {STORAGE_ROOT}")


asyncio.run(main())
