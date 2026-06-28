"""The ``list`` verb: enumerate registry packages annotated with sweep status.

Pure logic — the validation-record read is injected so this is unit-testable.
"""

from __future__ import annotations

from typing import Callable

from .registry import RegistryError

LIST_COLUMNS = [
    ("package", "PACKAGE"),
    ("repo", "REPO"),
    ("ref", "REF"),
    ("tags", "TAGS"),
    ("status", "STATUS"),
    ("autoware", "AUTOWARE"),
    ("validated", "VALIDATED"),
]


def _date(at) -> str:
    return (at or "")[:10] if isinstance(at, str) else ""


def evaluate(
    selection: list[tuple[str, dict, list[str]]],
    *,
    fetch_record: Callable[[str], dict | None],
    strict: bool = False,
) -> list[dict]:
    """Build one row per selected package, annotated with its latest sweep record.

    ``selection`` is the ``(key, spec, names)`` output of
    :func:`compose.select_repositories`. Each row's ``problem`` flag is ``True``
    when the package's latest validation is ``fail`` or there is no record — used
    by ``--strict`` to decide the exit code. ``fetch_record`` failures are caught
    per package and shown as an unknown status.
    """
    rows: list[dict] = []
    for key, spec, names in selection:
        ref = spec.get("ref") or {}
        ref_display = f"{ref.get('kind', '?')} {ref.get('value', '')}".strip()
        package_specs = spec.get("packages") or {}
        for name in names:
            tags = ", ".join((package_specs.get(name) or {}).get("tags") or [])
            try:
                record = fetch_record(name)
            except RegistryError:
                record = None
            if record is None:
                status, autoware, validated = "—", "", ""
            else:
                status = record.get("status") or "—"
                autoware = record.get("autoware_version") or ""
                validated = _date(record.get("at"))
            rows.append(
                {
                    "package": name,
                    "repo": key,
                    "ref": ref_display,
                    "tags": tags,
                    "status": status,
                    "autoware": autoware,
                    "validated": validated,
                    "problem": status != "pass",
                }
            )
    return rows
