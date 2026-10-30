"""Issue an API token for a user. The token is printed ONCE; only its hash is stored."""

import asyncio
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from blueprint_mcp.auth import hash_token, new_token
from blueprint_mcp.server import DATABASE_URL


async def main(email: str, label: str, days: int | None) -> None:
    token = new_token()
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        result = await conn.execute(
            text("""
                INSERT INTO api_tokens (tenant_id, user_id, token_hash, label, expires_at)
                SELECT tenant_id, id, :h, :label,
                       CASE WHEN CAST(:days AS int) IS NULL THEN NULL
                            ELSE now() + make_interval(days => CAST(:days AS int)) END
                FROM users WHERE email = :email
                RETURNING id"""),
            {"h": hash_token(token), "label": label, "days": days, "email": email},
        )
        if result.first() is None:
            sys.exit(f"no such user: {email}")
    await engine.dispose()
    print(token)


if __name__ == "__main__":
    email, label = sys.argv[1], sys.argv[2]
    days = int(sys.argv[3]) if len(sys.argv) > 3 else None
    asyncio.run(main(email, label, days))
