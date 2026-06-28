"""Render ``check``/``list`` result rows as a text table or JSON."""

from __future__ import annotations

import json


def render_table(rows: list[dict], columns: list[tuple[str, str]]) -> str:
    """Render ``rows`` as a fixed-width table.

    ``columns`` is a list of ``(key, header)`` pairs; each row's ``key`` value is
    shown under ``header``. Column width is the max of the header and the cell
    values. Returns an empty string for no rows.
    """
    if not rows:
        return ""
    widths = [
        max(len(header), *(len(str(row.get(key, ""))) for row in rows))
        for key, header in columns
    ]

    def line(values: list) -> str:
        cells = (str(v).ljust(w) for v, w in zip(values, widths))
        return "  ".join(cells).rstrip()

    out = [line([header for _, header in columns])]
    out += [line([row.get(key, "") for key, _ in columns]) for row in rows]
    return "\n".join(out)


def render_json(payload) -> str:
    """Serialize ``payload`` as pretty JSON (stable key order as inserted)."""
    return json.dumps(payload, indent=2, sort_keys=False)
