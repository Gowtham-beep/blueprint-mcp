import hashlib
import secrets

from mcp.server.auth.provider import AccessToken
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

TOKEN_PREFIX = "bpk_"


def new_token() -> str:
    """A fresh random token: 256 bits, URL-safe. Shown once, never stored."""
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


VERIFY_SQL = text("""
    SELECT user_id, expires_at
    FROM api_tokens
    WHERE token_hash = :token_hash
      AND revoked_at IS NULL
      AND (expires_at IS NULL OR expires_at > now())
""")


class DbTokenVerifier:
    """Runs on every HTTP request, before any tool code."""

    def __init__(self, engine: AsyncEngine, resource: str) -> None:
        self._engine = engine
        self._resource = resource  # the URL of THIS server; tokens are only valid here

    async def verify_token(self, token: str) -> AccessToken | None:
        token_hash = hash_token(token)
        async with self._engine.connect() as conn:
            row = (await conn.execute(VERIFY_SQL, {"token_hash": token_hash})).first()
        if row is None:
            return None
        return AccessToken(
            token=token_hash[:12],  # never keep the raw token around
            client_id=str(row.user_id),
            scopes=[],
            expires_at=int(row.expires_at.timestamp()) if row.expires_at else None,
            resource=self._resource,
            subject=str(row.user_id),
        )