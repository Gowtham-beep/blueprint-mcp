import pytest

from blueprint_mcp.storage import StorageError, resolve_storage_path


@pytest.fixture
def root(tmp_path):
    root = tmp_path / "storage"
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "ok.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "secret.txt").write_text("secret")  # real file OUTSIDE the root
    return root


def test_normal_file_resolves(root):
    assert resolve_storage_path("docs/ok.pdf", root).name == "ok.pdf"


def test_dotdot_escape_is_rejected(root):
    with pytest.raises(StorageError):
        resolve_storage_path("../secret.txt", root)


def test_absolute_path_is_rejected(root):
    outside = root.parent / "secret.txt"
    with pytest.raises(StorageError):
        resolve_storage_path(str(outside), root)


def test_symlink_escape_is_rejected(root, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside") / "secret.txt"
    outside.write_text("secret")
    (root / "docs" / "link.pdf").symlink_to(outside)
    with pytest.raises(StorageError):
        resolve_storage_path("docs/link.pdf", root)


def test_missing_file_is_rejected(root):
    with pytest.raises(StorageError):
        resolve_storage_path("docs/nope.pdf", root)
