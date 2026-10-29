import os
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from mcp.server.auth.middleware.auth_context import get_access_token
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


class AuthError(Exception):
    pass


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    tenant_id: UUID
    role: str

    def visible_statuses(self) -> list[str]:
        if self.role == "viewer":
            return ["approved"]
        return ["draft", "in_review", "approved", "superseded"]


# Fail closed: unless startup says otherwise, identity must come from a verified token.
_identity_mode: Literal["env", "token"] = "token"


def configure_identity(mode: Literal["env", "token"]) -> None:
    global _identity_mode
    _identity_mode = mode


async def resolve_principal(engine: AsyncEngine) -> Principal:
    if _identity_mode == "env":
        email = os.environ.get("BLUEPRINT_USER_EMAIL")
        if not email:
            raise AuthError("not authenticated")
        where, value = "email = :v", email
    else:
        token = get_access_token()
        if token is None or token.subject is None:
            raise AuthError("not authenticated")
        try:
            where, value = "id = :v", UUID(token.subject)
        except ValueError:
            raise AuthError("not authenticated") from None

    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(f"SELECT id, tenant_id, role FROM users WHERE {where}"), {"v": value}
            )
        ).first()
    if row is None:
        raise AuthError("not authenticated")
    return Principal(user_id=row.id, tenant_id=row.tenant_id, role=row.role)