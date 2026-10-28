import os
from pathlib import Path

STORAGE_ROOT = Path(os.environ.get("STORAGE_ROOT", "storage")).resolve()


class StorageError(Exception):
    pass


def resolve_storage_path(relative: str, root: Path = STORAGE_ROOT) -> Path:
    """Map a DB-recorded relative path to a real file, refusing to leave `root`."""
    root = root.resolve()
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root):
        raise StorageError("path escapes storage root")
    if not candidate.is_file():
        raise StorageError("file missing")
    return candidate