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


def discover_repos_files(
    start: str | Path = ".", name: str = "autoware-index"
) -> list[Path]:
    """Find ``<name>.repos`` in ``start`` or one level deep, for auto-discovery.

    A file directly in ``start`` wins outright (returned as the sole match). Only
    when there is none there do we look one level deep (``start/*/<name>.repos``),
    which covers compose's default ``repositories/<name>.repos`` output. Returns
    all candidates found (sorted); the caller decides what 0, 1, or >1 means.
    """
    start_path = Path(start)
    direct = start_path / f"{name}.repos"
    if direct.is_file():
        return [direct]
    return sorted(p for p in start_path.glob(f"*/{name}.repos") if p.is_file())
