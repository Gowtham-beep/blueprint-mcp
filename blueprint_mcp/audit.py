import logging
from uuid import UUID

from mcp.server.auth.middleware.auth_context import get_access_token
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from blueprint_mcp.principal import Principal

log = logging.getLogger("blueprint.audit")

INSERT_SQL = text("""
    INSERT INTO audit_log (event, outcome, reason, tenant_id, user_id, token_ref, tool, target)
    VALUES (:event, :outcome, :reason, :tenant_id, :user_id, :token_ref, :tool, :target)
""")


def safe_target(value: object) -> str:
    """Caller input never goes into the log raw: only a parsed UUID, or a fixed marker."""
    try:
        return str(UUID(str(value)))
    except ValueError:
        return "invalid-id"


def current_token_ref() -> str | None:
    """The safe token identifier (hash prefix) of the request being served, if any."""
    token = get_access_token()
    return token.token if token else None


async def record(
    engine: AsyncEngine,
    *,
    event: str,
    outcome: str,
    reason: str,
    principal: Principal | None = None,
    token_ref: str | None = None,
    tool: str | None = None,
    target: object | None = None,
) -> None:
    """Write one audit row on its OWN connection, so it survives the request's rollback.

    Failing open on purpose: if the audit write fails we log loudly and carry on.
    """
    try:
        async with engine.begin() as conn:
            await conn.execute(
                INSERT_SQL,
                {
                    "event": event,
                    "outcome": outcome,
                    "reason": reason,
                    "tenant_id": principal.tenant_id if principal else None,
                    "user_id": principal.user_id if principal else None,
                    "token_ref": token_ref if token_ref is not None else current_token_ref(),
                    "tool": tool,
                    "target": safe_target(target) if target is not None else None,
                },
            )
    except Exception:
        log.exception("audit write failed")