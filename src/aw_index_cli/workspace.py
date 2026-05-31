"""Discover the workspace repo root and the output ``.repos`` path."""

from __future__ import annotations

from pathlib import Path


def find_repo_root(start: str | Path) -> Path:
    """Walk up from ``start`` to the first ancestor containing ``repositories/``.

    The search includes ``start`` itself. If no such directory is found, the
    resolved ``start`` is returned unchanged.
    """
    start_path = Path(start).resolve()
    for candidate in [start_path, *start_path.parents]:
        if (candidate / "repositories").is_dir():
            return candidate
    return start_path


def output_path(repo_root: str | Path, name: str = "autoware-index") -> Path:
    """Return ``<repo_root>/repositories/<name>.repos``."""
    return Path(repo_root) / "repositories" / f"{name}.repos"
