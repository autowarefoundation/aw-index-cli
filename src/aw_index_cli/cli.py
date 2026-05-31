"""Command-line interface for aw-index-cli."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .compose import ComposeError, provenance_header, render_repos, select_packages
from .registry import RegistryError, describe_source, load_distribution
from .workspace import find_repo_root, output_path

STUB_COMMANDS = ("import", "sync", "check", "refresh")


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
    compose.add_argument("--tags", nargs="*")
    compose.add_argument(
        "--autoware",
        help=(
            "informational only — recorded in the header; the registry tracks "
            "one ref per package and does not resolve by Autoware version"
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

    for name in STUB_COMMANDS:
        stub = sub.add_parser(name, help=f"(not implemented) {name}")
        stub.set_defaults(func=_make_stub(name))

    return parser


def _make_stub(name: str):
    def _run(_args: argparse.Namespace) -> int:
        print(f"aw-index-cli {name} is not implemented yet", file=sys.stderr)
        return 2

    return _run


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
        header_lines = provenance_header(
            tool_version=__version__,
            ros_distro=args.rosdistro,
            source=source,
            tags=args.tags,
            autoware=args.autoware,
            generated_at=generated_at,
        )
        text = render_repos(distribution, tags=args.tags, header_lines=header_lines)
    except (RegistryError, ComposeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

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

    count = len(select_packages(distribution, tags=args.tags))
    print(f"Wrote {count} package(s) to {path}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 2
    return args.func(args)
