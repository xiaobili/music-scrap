from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path


class PathViolation(Exception):
    """Raised when a path escapes the configured library roots."""


def resolve_inside_roots(
    raw: str | Path,
    roots: Iterable[Path],
    *,
    must_exist: bool = True,
    must_be_dir: bool = False,
) -> Path:
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        raise PathViolation("absolute path required")

    resolved = candidate.resolve(strict=False)
    for root in roots:
        root_resolved = Path(root).expanduser().resolve(strict=False)
        if resolved == root_resolved or root_resolved in resolved.parents:
            if must_exist and not resolved.exists():
                raise PathViolation(f"path does not exist: {resolved}")
            if must_be_dir and not resolved.is_dir():
                raise PathViolation(f"not a directory: {resolved}")
            return resolved
    raise PathViolation("path is outside configured library roots")


def is_inside_roots(raw: str | Path, roots: Iterable[Path]) -> bool:
    try:
        resolve_inside_roots(raw, roots, must_exist=False)
        return True
    except PathViolation:
        return False


def relative_to_root(path: Path, root: Path) -> str:
    try:
        return Path(os.path.relpath(path, root)).as_posix()
    except ValueError as exc:  # pragma: no cover - defensive
        raise PathViolation(str(exc)) from exc
