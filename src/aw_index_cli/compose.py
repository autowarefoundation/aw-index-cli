"""Select repositories from a distribution and render a vcs ``.repos`` file."""

from __future__ import annotations

import yaml


class ComposeError(Exception):
    """Raised when a distribution cannot be composed into ``.repos`` entries."""


def _reject_unknown(singular: str, plural: str, missing: set[str]) -> None:
    """Raise :class:`ComposeError` naming any explicitly-requested unknowns."""
    if missing:
        names = ", ".join(repr(name) for name in sorted(missing))
        label = singular if len(missing) == 1 else plural
        raise ComposeError(f"no such {label} in the distribution: {names}")


def select_repositories(
    distribution: dict,
    tags: list[str] | None = None,
    *,
    packages: list[str] | None = None,
    repository: list[str] | None = None,
) -> list[tuple[str, dict, list[str]]]:
    """Return ``(key, spec, selected_packages)`` triples sorted by repo key.

    Three optional filters narrow the selection and are ANDed together; omit
    all of them to select the whole distribution:

    * ``tags`` — keep packages whose own ``tags`` intersect these.
    * ``packages`` — keep packages whose name is in this list.
    * ``repository`` — keep only these repository entries (by registry key).

    A repository is selected when at least one of its packages survives every
    given filter; its ``selected_packages`` names are sorted. An explicit
    ``repository`` key or ``packages`` name that is absent from the *whole*
    distribution (independent of the other filters, so a typo never hides
    behind an empty result) raises :class:`ComposeError`, as does a selected
    repository whose ``packages`` is not a mapping.
    """
    all_repos = distribution.get("repositories") or {}
    wanted_tags = set(tags or [])
    wanted_pkgs = set(packages or [])
    wanted_repos = set(repository or [])

    # Validate explicit names against the entire distribution before filtering,
    # so an unknown name errors loudly rather than yielding silent-empty output.
    known_pkgs: set[str] = set()
    for spec in all_repos.values():
        spec_pkgs = (spec or {}).get("packages")
        if isinstance(spec_pkgs, dict):
            known_pkgs.update(spec_pkgs)
    _reject_unknown(
        "repository entry", "repository entries", wanted_repos - set(all_repos)
    )
    _reject_unknown("package", "packages", wanted_pkgs - known_pkgs)

    selected = []
    for key, spec in sorted(all_repos.items()):
        if wanted_repos and key not in wanted_repos:
            continue
        spec_pkgs = (spec or {}).get("packages") or {}
        if not isinstance(spec_pkgs, dict):
            raise ComposeError(
                f"repository {key!r} has 'packages' that is not a mapping "
                f"of package name to spec (got {type(spec_pkgs).__name__})"
            )
        names = sorted(
            name
            for name, pkg in spec_pkgs.items()
            if (not wanted_tags or set((pkg or {}).get("tags") or []) & wanted_tags)
            and (not wanted_pkgs or name in wanted_pkgs)
        )
        if names:
            selected.append((key, spec, names))
    return selected


def to_repos_entries(repositories: list[tuple[str, dict, list[str]]]) -> dict:
    """Map selected repositories to an ordered ``key -> entry`` dict.

    The entry key is the registry repository key, so packages from one
    monorepo collapse into a single clone. Each entry carries exactly
    vcstool's ``type``/``url``/``version`` and nothing else — the format
    defines no other per-entry fields. The selected registered package names
    are recorded in the provenance header comments (see
    :func:`provenance_header`), not in the YAML body. Raises
    :class:`ComposeError` when a repository is missing ``url`` or
    ``ref.value``, or when its ``ref`` is not a mapping.
    """
    entries: dict = {}
    for key, spec, _names in repositories:
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
        }
    return entries


def provenance_header(
    *,
    tool_version: str,
    ros_distro: str,
    source: str,
    tags: list[str] | None = None,
    packages: list[str] | None = None,
    repository: list[str] | None = None,
    autoware: str | None = None,
    generated_at: str | None = None,
    selection: list[tuple[str, list[str]]] | None = None,
) -> list[str]:
    """Build the ``# …`` comment lines that precede the rendered ``.repos``.

    The ``packages`` and ``repository`` selection filters, when given, are
    recorded so the file documents how it was produced. ``selection`` is the
    ``(repo_key, selected_package_names)`` listing; when given, every entry is
    named in the header with its selected packages.
    """
    lines = [
        f"# aw-index-cli {tool_version}",
        f"# source: {source}",
        f"# rosdistro: {ros_distro}",
        f"# tags: {', '.join(tags) if tags else 'all'}",
    ]
    if packages:
        lines.append(f"# packages: {', '.join(packages)}")
    if repository:
        lines.append(f"# repository: {', '.join(repository)}")
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
    packages: list[str] | None = None,
    repository: list[str] | None = None,
    header_lines: list[str],
) -> str:
    """Render the full ``.repos`` document (header comments + YAML body)."""
    repositories = select_repositories(
        distribution, tags=tags, packages=packages, repository=repository
    )
    entries = to_repos_entries(repositories)
    body = yaml.safe_dump(
        {"repositories": entries},
        sort_keys=False,
        default_flow_style=False,
    )
    return "\n".join(header_lines) + "\n" + body
