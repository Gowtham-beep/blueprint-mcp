import os
from dataclasses import dataclass
from uuid import UUID

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


async def resolve_principal(engine: AsyncEngine) -> Principal:
    email = os.environ.get("BLUEPRINT_USER_EMAIL")
    if not email:
        raise AuthError("not Authenticated")
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text("SELECT id, tenant_id, role FROM users WHERE email = :email"),
                {"email": email},
            )
        ).first()
    if row is None:
        raise AuthError("not Authenticated")
    return Principal(user_id=row.id, tenant_id=row.tenant_id, role=row.role)
