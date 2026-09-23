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
    include_dependencies: bool = True,
    reference_design: bool = False,
) -> list[tuple[str, dict, list[str]]]:
    """Return ``(key, spec, selected_packages)`` triples sorted by repo key.

    Four optional filters narrow the selection and are ANDed together; omit
    all of them to select the whole distribution:

    * ``tags``: keep packages whose own ``tags`` intersect these.
    * ``packages``: keep packages whose name is in this list.
    * ``repository``: keep only these repository entries (by registry key).
    * ``reference_design``: keep only entries marked as a reference design.

    A repository is selected when at least one of its packages survives every
    given filter. For a v4 distribution, the selected packages then pull in
    their transitive ``index_dependencies``, even when those dependencies do
    not match the filters. ``include_dependencies=False`` keeps the original
    filtered selection for commands such as ``list``. Package names within
    each repository are sorted. An explicit
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
    _reject_unknown("repository entry", "repository entries", wanted_repos - set(all_repos))
    _reject_unknown("package", "packages", wanted_pkgs - known_pkgs)

    selected = []
    for key, spec in sorted(all_repos.items()):
        if wanted_repos and key not in wanted_repos:
            continue
        marker = (spec or {}).get("reference_design")
        if marker is not None and not isinstance(marker, bool):
            raise ComposeError(
                f"repository {key!r} has 'reference_design' that is not a boolean "
                f"(got {type(marker).__name__})"
            )
        if reference_design and not marker:
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
    if include_dependencies and distribution.get("schema_version") == "4" and selected:
        return _with_index_dependencies(all_repos, selected)
    return selected


def _with_index_dependencies(
    all_repos: dict, selected: list[tuple[str, dict, list[str]]]
) -> list[tuple[str, dict, list[str]]]:
    """Expand filtered roots to their full v4 package dependency closure."""
    owners: dict[str, tuple[str, dict]] = {}
    for repo_key, repo in sorted(all_repos.items()):
        package_specs = (repo or {}).get("packages") or {}
        if not isinstance(package_specs, dict):
            continue  # A selected malformed repository already fails above.
        for name, package_spec in package_specs.items():
            if name in owners:
                raise ComposeError(f"package {name!r} is registered by multiple repositories")
            owners[name] = (repo_key, package_spec if package_spec is not None else {})

    included = {name for _key, _spec, names in selected for name in names}
    visited: set[str] = set()
    visiting: list[str] = []

    def visit(name: str) -> None:
        if name in visiting:
            cycle = visiting[visiting.index(name) :] + [name]
            raise ComposeError(f"index dependency cycle: {' -> '.join(cycle)}")
        if name in visited:
            return
        repo_key, package_spec = owners[name]
        if not isinstance(package_spec, dict):
            raise ComposeError(f"package {name!r} in repository {repo_key!r} is not a mapping")
        dependencies = package_spec.get("index_dependencies", [])
        if not isinstance(dependencies, list) or any(
            not isinstance(dependency, str) for dependency in dependencies
        ):
            raise ComposeError(
                f"package {name!r} has invalid 'index_dependencies' "
                "(expected a list of package names)"
            )
        visiting.append(name)
        for dependency in sorted(dependencies):
            if dependency not in owners:
                raise ComposeError(
                    f"index dependency {dependency!r} of package {name!r} is not registered"
                )
            included.add(dependency)
            visit(dependency)
        visiting.pop()
        visited.add(name)

    for name in sorted(included):
        visit(name)

    by_repo: dict[str, list[str]] = {}
    for name in included:
        repo_key, _package_spec = owners[name]
        by_repo.setdefault(repo_key, []).append(name)
    return [(key, all_repos[key], sorted(names)) for key, names in sorted(by_repo.items())]


def unknown_tags(distribution: dict, tags: list[str] | None) -> list[str]:
    """Return the requested tags that no package in the distribution carries.

    Sorted for stable output. Unlike an unknown ``--packages`` name or
    ``--repository`` key, an unknown tag is not a hard error: the tag
    vocabulary lives in the registry, not in the distribution file, so a
    valid id may simply have no usage yet. The CLI reports these as a
    stderr warning while still composing the (possibly empty) output.
    """
    if not tags:
        return []
    carried: set[str] = set()
    for spec in (distribution.get("repositories") or {}).values():
        spec_pkgs = (spec or {}).get("packages")
        if not isinstance(spec_pkgs, dict):
            continue
        for pkg in spec_pkgs.values():
            carried.update((pkg or {}).get("tags") or [])
    return sorted(set(tags) - carried)


def to_repos_entries(repositories: list[tuple[str, dict, list[str]]]) -> dict:
    """Map selected repositories to an ordered ``key -> entry`` dict.

    The entry key is the registry repository key, so packages from one
    monorepo collapse into a single clone. Each entry carries exactly
    vcs2l's ``type``/``url``/``version`` and nothing else; the format
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
    reference_design: bool = False,
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
    if reference_design:
        lines.append("# reference_design: true")
    if autoware is not None:
        lines.append(
            f"# autoware: {autoware} "
            "(informational only, not a ref selector; the registry tracks "
            "one ref per repository)"
        )
    if generated_at is not None:
        lines.append(f"# generated_at: {generated_at}")
    if selection:
        lines.append("# selected packages by repository:")
        for key, package_names in selection:
            lines.append(f"#   {key}: {', '.join(package_names)}")
    lines.append(
        "# Generated file. Re-run 'aw-index-cli compose …' to update; " "do not edit by hand."
    )
    return lines


def render_repos(
    distribution: dict,
    *,
    tags: list[str] | None = None,
    packages: list[str] | None = None,
    repository: list[str] | None = None,
    reference_design: bool = False,
    header_lines: list[str],
) -> str:
    """Render the full ``.repos`` document (header comments + YAML body).

    A blank line separates the ``#`` provenance header from the YAML body so the
    two read as distinct sections.
    """
    repositories = select_repositories(
        distribution,
        tags=tags,
        packages=packages,
        repository=repository,
        reference_design=reference_design,
    )
    entries = to_repos_entries(repositories)
    body = yaml.safe_dump(
        {"repositories": entries},
        sort_keys=False,
        default_flow_style=False,
    )
    return "\n".join(header_lines) + "\n\n" + body
