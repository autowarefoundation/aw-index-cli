"""The ``check`` verb: gate a composed ``.repos`` against the registry + history.

Pure logic — the network reads (validation records, live branch SHA) are passed in
as callables so the evaluation is unit-testable without I/O.
"""

from __future__ import annotations

import re
from typing import Callable

import yaml

from .registry import RegistryError

CHECK_COLUMNS = [
    ("package", "PACKAGE"),
    ("status", "STATUS"),
    ("autoware", "AUTOWARE"),
    ("ref", "REF"),
    ("validated", "VALIDATED"),
    ("note", "NOTE"),
]

_ROSDISTRO_RE = re.compile(r"^#\s*rosdistro:\s*(\S+)\s*$", re.MULTILINE)
_SELECTION_HEADER = "# selected packages by repository:"
_SELECTION_LINE_RE = re.compile(r"^#\s{2,}(\S+):\s*(.*)$")


class CheckError(Exception):
    """Raised when a ``.repos`` file cannot be read or parsed for checking."""


def parse_repos(text: str) -> dict:
    """Parse a vcstool ``.repos`` document → ``{repo_key: {url, version}}``."""
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise CheckError(f"invalid .repos YAML: {exc}") from exc
    repositories = (doc or {}).get("repositories")
    if not isinstance(repositories, dict):
        raise CheckError("no 'repositories' mapping found in .repos file")
    out: dict = {}
    for key, entry in repositories.items():
        entry = entry or {}
        out[key] = {"url": entry.get("url"), "version": entry.get("version")}
    return out


def rosdistro_from_header(text: str) -> str | None:
    """Return the rosdistro recorded in a generated ``.repos`` header, if any."""
    match = _ROSDISTRO_RE.search(text)
    return match.group(1) if match else None


def selected_packages_from_header(text: str) -> dict[str, list[str]]:
    """Parse the ``# selected packages by repository:`` block → ``{key: [pkgs]}``."""
    result: dict[str, list[str]] = {}
    lines = text.splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if ln.strip() == _SELECTION_HEADER)
    except StopIteration:
        return result
    for ln in lines[start + 1 :]:
        match = _SELECTION_LINE_RE.match(ln)
        if not match:
            break
        key, names = match.group(1), match.group(2).strip()
        result[key] = [n.strip() for n in names.split(",") if n.strip()]
    return result


def _date(at) -> str:
    return (at or "")[:10] if isinstance(at, str) else ""


def evaluate(
    repos: dict,
    distribution: dict,
    selected_by_key: dict[str, list[str]],
    *,
    fetch_record: Callable[[str], dict | None],
    resolve_sha: Callable[[str, str], str | None],
    strict: bool = False,
) -> list[dict]:
    """Evaluate each ``.repos`` repo against the registry and history.

    Returns one row dict per checked package (or one per removed repo). Each row
    carries a boolean ``problem`` flag: ``True`` for a failing validation, a ref
    drift (registry moved off your pin), or a removed repo; and — only when
    ``strict`` — also for an unvalidated package or a branch that advanced past the
    last swept SHA. ``fetch_record`` may raise :class:`RegistryError`; it is caught
    per package and surfaced as an unknown status rather than aborting the report.
    """
    registry = distribution.get("repositories") or {}
    rows: list[dict] = []
    for key in sorted(repos):
        your_ref = repos[key].get("version") or ""
        spec = registry.get(key)
        if spec is None:
            rows.append(
                {
                    "package": key,
                    "status": "—",
                    "autoware": "",
                    "ref": your_ref or "—",
                    "validated": "",
                    "note": "removed from registry",
                    "problem": True,
                }
            )
            continue

        ref = spec.get("ref") or {}
        reg_ref = ref.get("value") or ""
        ref_kind = ref.get("kind")
        url = spec.get("url") or ""
        ref_drift = bool(reg_ref) and your_ref != reg_ref
        ref_display = f"{your_ref} → {reg_ref}" if ref_drift else (your_ref or "—")

        packages = selected_by_key.get(key) or sorted(spec.get("packages") or {})

        live_sha = None
        if ref_kind == "branch" and url and reg_ref and not ref_drift:
            live_sha = resolve_sha(url, reg_ref)

        for package in packages:
            notes: list[str] = []
            problem = False
            if ref_drift:
                notes.append("registry moved")
                problem = True

            try:
                record = fetch_record(package)
                fetch_failed = False
            except RegistryError:
                record = None
                fetch_failed = True

            if record is None:
                status, autoware, validated = "—", "", ""
                notes.append("status fetch failed" if fetch_failed else "unvalidated")
                if strict:
                    problem = True
            else:
                status = record.get("status") or "—"
                autoware = record.get("autoware_version") or ""
                validated = _date(record.get("at"))
                if status == "fail":
                    problem = True
                swept_sha = record.get("resolved_sha")
                if live_sha and swept_sha and live_sha != swept_sha:
                    notes.append("branch advanced since sweep")
                    if strict:
                        problem = True

            rows.append(
                {
                    "package": package,
                    "status": status,
                    "autoware": autoware,
                    "ref": ref_display,
                    "validated": validated,
                    "note": "; ".join(notes),
                    "problem": problem,
                }
            )
    return rows
