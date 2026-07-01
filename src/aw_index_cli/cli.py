"""Command-line interface for aw-index-cli."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .check import (
    CHECK_COLUMNS,
    CheckError,
    evaluate as check_evaluate,
    parse_repos,
    rosdistro_from_header,
    selected_packages_from_header,
)
from .compose import (
    ComposeError,
    provenance_header,
    render_repos,
    select_repositories,
)
from .gitref import remote_sha
from .history import DEFAULT_DATA_REF, latest_record
from .listing import LIST_COLUMNS, evaluate as list_evaluate
from .registry import (
    DEFAULT_REF,
    DEFAULT_REPO,
    RegistryError,
    describe_source,
    load_distribution,
)
from .report import render_json, render_table
from .workspace import discover_repos_files, find_repo_root, output_path


def _add_registry_source_args(parser: argparse.ArgumentParser) -> None:
    """Add the shared --registry-path/--registry-repo/--registry-ref options."""
    parser.add_argument("--registry-path")
    parser.add_argument("--registry-repo", default=DEFAULT_REPO)
    parser.add_argument("--registry-ref", default=DEFAULT_REF)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aw-index-cli",
        description="Consumer CLI for the autoware-index registry.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"aw-index-cli {__version__}",
    )
    sub = parser.add_subparsers(dest="command")

    compose = sub.add_parser(
        "compose",
        help="Render a .repos file from a distribution.",
    )
    compose.add_argument("--rosdistro", required=True)
    compose.add_argument(
        "--packages",
        nargs="*",
        help="select only these registered package names (ANDed with other filters)",
    )
    compose.add_argument(
        "--repository",
        nargs="*",
        help="select only these repository entries by registry key",
    )
    compose.add_argument("--tags", nargs="*")
    compose.add_argument(
        "--autoware",
        help=(
            "informational only — recorded in the header; the registry tracks "
            "one ref per repository and does not resolve by Autoware version"
        ),
    )
    compose.add_argument("--registry-path")
    compose.add_argument("--registry-repo", default="autowarefoundation/autoware-index")
    compose.add_argument("--registry-ref", default="main")
    compose.add_argument("--repo-root")
    compose.add_argument("--name", default="autoware-index")
    compose.add_argument("--output", help="explicit output file path")
    compose.add_argument("--stdout", action="store_true")
    compose.add_argument("--no-timestamp", action="store_true")
    compose.set_defaults(func=_cmd_compose)

    check = sub.add_parser(
        "check",
        help="Gate a .repos against the registry and sweep history.",
    )
    check.add_argument(
        "--repos",
        help="path to the .repos file (default: auto-discover autoware-index.repos)",
    )
    check.add_argument(
        "--rosdistro",
        help="ROS distribution (default: read from the .repos header)",
    )
    _add_registry_source_args(check)
    check.add_argument("--data-ref", default=DEFAULT_DATA_REF)
    check.add_argument("--strict", action="store_true")
    check.add_argument("--format", choices=("table", "json"), default="table")
    check.set_defaults(func=_cmd_check)

    listing = sub.add_parser(
        "list",
        help="List registry packages with their latest sweep status.",
    )
    listing.add_argument("--rosdistro", required=True)
    listing.add_argument("--packages", nargs="*")
    listing.add_argument("--repository", nargs="*")
    listing.add_argument("--tags", nargs="*")
    _add_registry_source_args(listing)
    listing.add_argument("--data-ref", default=DEFAULT_DATA_REF)
    listing.add_argument("--strict", action="store_true")
    listing.add_argument("--format", choices=("table", "json"), default="table")
    listing.set_defaults(func=_cmd_list)

    return parser


def _cmd_compose(args: argparse.Namespace) -> int:
    try:
        distribution = load_distribution(
            args.rosdistro,
            path=args.registry_path,
            repo=args.registry_repo,
            ref=args.registry_ref,
        )
        source = describe_source(
            path=args.registry_path,
            repo=args.registry_repo,
            ref=args.registry_ref,
        )
        if args.no_timestamp:
            generated_at = None
        else:
            generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        selection = [
            (key, names)
            for key, _spec, names in select_repositories(
                distribution,
                tags=args.tags,
                packages=args.packages,
                repository=args.repository,
            )
        ]
        header_lines = provenance_header(
            tool_version=__version__,
            ros_distro=args.rosdistro,
            source=source,
            tags=args.tags,
            packages=args.packages,
            repository=args.repository,
            autoware=args.autoware,
            generated_at=generated_at,
            selection=selection,
        )
        text = render_repos(
            distribution,
            tags=args.tags,
            packages=args.packages,
            repository=args.repository,
            header_lines=header_lines,
        )
    except (RegistryError, ComposeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.stdout:
        print(text)
        return 0

    if args.output:
        path = Path(args.output)
    else:
        repo_root = find_repo_root(args.repo_root or Path.cwd())
        path = output_path(repo_root, args.name)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

    repo_count = len(selection)
    package_count = sum(len(names) for _, names in selection)
    noun = "entry" if repo_count == 1 else "entries"
    listing = ", ".join(
        f"{key} ({', '.join(names)})" for key, names in selection
    )
    summary = (
        f"Wrote {repo_count} repository {noun} covering "
        f"{package_count} registered package(s) to {path}"
    )
    if listing:
        summary += f": {listing}"
    print(summary, file=sys.stderr)
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    try:
        if args.repos:
            repos_path = Path(args.repos)
            if not repos_path.is_file():
                raise CheckError(f".repos file not found: {repos_path}")
        else:
            matches = discover_repos_files()
            if not matches:
                raise CheckError(
                    "no autoware-index.repos found in the current directory or one "
                    "level deep; pass --repos"
                )
            if len(matches) > 1:
                found = ", ".join(str(p) for p in matches)
                raise CheckError(
                    f"multiple autoware-index.repos found ({found}); pass --repos"
                )
            repos_path = matches[0]

        try:
            text = repos_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise CheckError(f"could not read {repos_path}: {exc}") from exc

        repos = parse_repos(text)
        ros_distro = args.rosdistro or rosdistro_from_header(text)
        if not ros_distro:
            raise CheckError(
                "could not determine the rosdistro; pass --rosdistro (the .repos "
                "header has no '# rosdistro:' line)"
            )
        distribution = load_distribution(
            ros_distro,
            path=args.registry_path,
            repo=args.registry_repo,
            ref=args.registry_ref,
        )
        selected = selected_packages_from_header(text)

        def fetch_record(package: str):
            return latest_record(
                package,
                ros_distro=ros_distro,
                repo=args.registry_repo,
                data_ref=args.data_ref,
            )

        rows = check_evaluate(
            repos,
            distribution,
            selected,
            fetch_record=fetch_record,
            resolve_sha=remote_sha,
            strict=args.strict,
        )
    except (RegistryError, CheckError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    problems = sum(1 for row in rows if row["problem"])
    if args.format == "json":
        print(
            render_json(
                {
                    "rosdistro": ros_distro,
                    "repos": str(repos_path),
                    "problems": problems,
                    "rows": rows,
                }
            )
        )
    else:
        table = render_table(rows, CHECK_COLUMNS)
        if table:
            print(table)
        print(f"{len(rows)} checked, {problems} problem(s)", file=sys.stderr)
    return 1 if problems else 0


def _cmd_list(args: argparse.Namespace) -> int:
    try:
        distribution = load_distribution(
            args.rosdistro,
            path=args.registry_path,
            repo=args.registry_repo,
            ref=args.registry_ref,
        )
        selection = select_repositories(
            distribution,
            tags=args.tags,
            packages=args.packages,
            repository=args.repository,
        )

        def fetch_record(package: str):
            return latest_record(
                package,
                ros_distro=args.rosdistro,
                repo=args.registry_repo,
                data_ref=args.data_ref,
            )

        rows = list_evaluate(selection, fetch_record=fetch_record, strict=args.strict)
    except (RegistryError, ComposeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    problems = sum(1 for row in rows if row["problem"])
    if args.format == "json":
        print(render_json({"rosdistro": args.rosdistro, "rows": rows}))
    else:
        table = render_table(rows, LIST_COLUMNS)
        if table:
            print(table)
        summary = f"{len(rows)} package(s)"
        if problems:
            summary += f", {problems} not passing"
        print(summary, file=sys.stderr)
    return 1 if (args.strict and problems) else 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 2
    return args.func(args)
