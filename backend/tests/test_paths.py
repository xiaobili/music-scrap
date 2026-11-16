from __future__ import annotations

import pytest

from app.core.paths import PathViolation, is_inside_roots, resolve_inside_roots


def test_accepts_path_inside_root(tmp_path):
    root = tmp_path / "library"
    root.mkdir()
    target = root / "album" / "track.flac"
    target.parent.mkdir()
    target.write_bytes(b"x")
    assert resolve_inside_roots(target, [root]) == target.resolve()


def test_rejects_traversal(tmp_path):
    root = tmp_path / "library"
    root.mkdir()
    with pytest.raises(PathViolation):
        resolve_inside_roots(tmp_path / "library" / ".." / "secret.flac", [root])


def test_rejects_symlink_escape(tmp_path):
    root = tmp_path / "library"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.flac"
    secret.write_bytes(b"x")
    link = root / "link.flac"
    link.symlink_to(secret)
    with pytest.raises(PathViolation):
        resolve_inside_roots(link, [root])
    assert is_inside_roots(link, [root]) is False


def test_requires_absolute_path(tmp_path):
    root = tmp_path / "library"
    root.mkdir()
    with pytest.raises(PathViolation):
        resolve_inside_roots("relative.flac", [root])
