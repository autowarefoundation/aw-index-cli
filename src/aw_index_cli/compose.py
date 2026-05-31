"""Select packages from a distribution and render a vcs ``.repos`` file."""

from __future__ import annotations

import yaml


class ComposeError(Exception):
    """Raised when a distribution cannot be composed into ``.repos`` entries."""


def select_packages(
    distribution: dict,
    tags: list[str] | None = None,
) -> list[tuple[str, dict]]:
    """Return ``(name, spec)`` pairs sorted by package name.

    When ``tags`` is non-empty, only packages whose own ``tags`` intersect the
    requested tags are kept. Empty or ``None`` ``tags`` selects every package.
    """
    packages = distribution.get("packages") or {}
    items = sorted(packages.items(), key=lambda kv: kv[0])
    if not tags:
        return items
    wanted = set(tags)
    selected = []
    for name, spec in items:
        pkg_tags = set((spec or {}).get("tags") or [])
        if pkg_tags & wanted:
            selected.append((name, spec))
    return selected


def _checkout_path(url: str) -> str:
    """Derive the clone path key from a repository URL's basename."""
    return url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")


def to_repos_entries(packages: list[tuple[str, dict]]) -> dict:
    """Map selected packages to an ordered ``path -> {type,url,version}`` dict.

    The path is the repository URL's basename, so packages from one monorepo
    collapse into a single clone. Raises :class:`ComposeError` when a package is
    missing ``repository`` or ``ref.value``, or when two packages share a
    repository but request different refs.
    """
    entries: dict = {}
    owners: dict = {}
    for name, spec in packages:
        spec = spec or {}
        repository = spec.get("repository")
        if not repository:
            raise ComposeError(f"package {name!r} is missing 'repository'")
        ref = spec.get("ref") or {}
        version = ref.get("value")
        if not version:
            raise ComposeError(f"package {name!r} is missing 'ref.value'")
        path = _checkout_path(repository)
        if path in entries:
            existing = entries[path]
            if existing["url"] == repository and existing["version"] == version:
                continue
            raise ComposeError(
                f"packages {owners[path]!r} and {name!r} share repository "
                f"{repository} but request different refs: "
                f"{existing['version']} vs {version}"
            )
        entries[path] = {
            "type": "git",
            "url": repository,
            "version": version,
        }
        owners[path] = name
    return {path: entries[path] for path in sorted(entries)}


def provenance_header(
    *,
    tool_version: str,
    ros_distro: str,
    source: str,
    tags: list[str] | None = None,
    autoware: str | None = None,
    generated_at: str | None = None,
) -> list[str]:
    """Build the ``# …`` comment lines that precede the rendered ``.repos``."""
    lines = [
        f"# aw-index-cli {tool_version}",
        f"# source: {source}",
        f"# rosdistro: {ros_distro}",
        f"# tags: {', '.join(tags) if tags else 'all'}",
    ]
    if autoware is not None:
        lines.append(
            f"# autoware: {autoware} "
            "(informational only — not a ref selector; the registry tracks "
            "one ref per package)"
        )
    if generated_at is not None:
        lines.append(f"# generated_at: {generated_at}")
    lines.append(
        "# Generated file — re-run 'aw-index-cli compose …' to update; "
        "do not edit by hand."
    )
    return lines


def render_repos(
    distribution: dict,
    *,
    tags: list[str] | None = None,
    header_lines: list[str],
) -> str:
    """Render the full ``.repos`` document (header comments + YAML body)."""
    packages = select_packages(distribution, tags=tags)
    entries = to_repos_entries(packages)
    body = yaml.safe_dump(
        {"repositories": entries},
        sort_keys=False,
        default_flow_style=False,
    )
    return "\n".join(header_lines) + "\n" + body
