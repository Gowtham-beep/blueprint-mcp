from dataclasses import dataclass

from blueprint_mcp.access import RevisionRow


@dataclass(frozen=True)
class Change:
    field: str
    from_value: str | None
    to_value: str | None


def _fmt(value: object) -> str | None:
    return None if value is None else str(value)


def diff_revisions(a: RevisionRow, b: RevisionRow) -> list[Change]:
    """Metadata differences only: status and approval details."""
    changes = []
    for field in ("status", "approved_by", "approved_at"):
        before, after = getattr(a, field), getattr(b, field)
        if before != after:
            changes.append(Change(field, _fmt(before), _fmt(after)))
    return changes


def elapsed_days(a: RevisionRow, b: RevisionRow) -> float:
    return round((b.created_at - a.created_at).total_seconds() / 86400, 2)
