"""Select repositories from a distribution and render a vcs ``.repos`` file."""

from __future__ import annotations

import yaml


class ComposeError(Exception):
    """Raised when a distribution cannot be composed into ``.repos`` entries."""


def select_repositories(
    distribution: dict,
    tags: list[str] | None = None,
) -> list[tuple[str, dict, list[str]]]:
    """Return ``(key, spec, selected_packages)`` triples sorted by repo key.

    A package is selected when ``tags`` is empty/``None`` or intersects the
    package's own ``tags``. A repository is selected when at least one of its
    packages is selected; its ``selected_packages`` names are sorted. Raises
    :class:`ComposeError` when a repository's ``packages`` is not a mapping.
    """
    repositories = distribution.get("repositories") or {}
    wanted = set(tags or [])
    selected = []
    for key, spec in sorted(repositories.items()):
        packages = (spec or {}).get("packages") or {}
        if not isinstance(packages, dict):
            raise ComposeError(
                f"repository {key!r} has 'packages' that is not a mapping "
                f"of package name to spec (got {type(packages).__name__})"
            )
        if not wanted:
            names = sorted(packages)
        else:
            names = sorted(
                name
                for name, pkg in packages.items()
                if set((pkg or {}).get("tags") or []) & wanted
            )
        if names:
            selected.append((key, spec, names))
    return selected


def to_repos_entries(repositories: list[tuple[str, dict, list[str]]]) -> dict:
    """Map selected repositories to an ordered ``key -> entry`` dict.

    The entry key is the registry repository key, so packages from one
    monorepo collapse into a single clone. Each entry carries vcstool's
    ``type``/``url``/``version`` plus a ``packages`` manifest naming the
    selected registered packages (vcstool ignores unknown keys). Raises
    :class:`ComposeError` when a repository is missing ``url`` or
    ``ref.value``, or when its ``ref`` is not a mapping.
    """
    entries: dict = {}
    for key, spec, package_names in repositories:
        spec = spec or {}
        url = spec.get("url")
        if not url:
            raise ComposeError(f"repository {key!r} is missing 'url'")
        ref = spec.get("ref") or {}
        if not isinstance(ref, dict):
            raise ComposeError(
                f"repository {key!r} has 'ref' that is not a mapping "
                f"with 'kind' and 'value' (got {type(ref).__name__})"
            )
        version = ref.get("value")
        if not version:
            raise ComposeError(f"repository {key!r} is missing 'ref.value'")
        entries[key] = {
            "type": "git",
            "url": url,
            "version": version,
            "packages": list(package_names),
        }
    return entries


def provenance_header(
    *,
    tool_version: str,
    ros_distro: str,
    source: str,
    tags: list[str] | None = None,
    autoware: str | None = None,
    generated_at: str | None = None,
    selection: list[tuple[str, list[str]]] | None = None,
) -> list[str]:
    """Build the ``# …`` comment lines that precede the rendered ``.repos``.

    ``selection`` is the ``(repo_key, selected_package_names)`` listing; when
    given, every entry is named in the header with its selected packages.
    """
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
            "one ref per repository)"
        )
    if generated_at is not None:
        lines.append(f"# generated_at: {generated_at}")
    if selection:
        lines.append("# selected packages by repository:")
        for key, package_names in selection:
            lines.append(f"#   {key}: {', '.join(package_names)}")
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
    repositories = select_repositories(distribution, tags=tags)
    entries = to_repos_entries(repositories)
    body = yaml.safe_dump(
        {"repositories": entries},
        sort_keys=False,
        default_flow_style=False,
    )
    return "\n".join(header_lines) + "\n" + body
