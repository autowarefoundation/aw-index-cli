"""Read validation history records from the registry's ``data`` branch."""

from __future__ import annotations

import json
from urllib.parse import quote

from .registry import DEFAULT_REPO, RegistryError, _fetch_text

DEFAULT_DATA_REF = "data"
HISTORY_URL = (
    "https://raw.githubusercontent.com/{repo}/{data_ref}"
    "/history/{ros_distro}/{package}.ndjson"
)


def latest_record(
    package: str,
    *,
    ros_distro: str,
    repo: str = DEFAULT_REPO,
    data_ref: str = DEFAULT_DATA_REF,
    timeout: float = 30,
) -> dict | None:
    """Return the latest validation record for ``package``, or ``None``.

    Fetches ``history/<ros_distro>/<package>.ndjson`` from the ``data`` branch and
    returns its last non-empty line parsed as JSON (the history is append-only, so
    the last line is the newest record). Returns ``None`` when the package has no
    history yet (HTTP 404) or the file is empty. Both schema-1 (no ``schema`` key)
    and schema-2 records are returned as-is. Raises :class:`RegistryError` on other
    fetch failures or when the latest line is not a JSON object.
    """
    url = HISTORY_URL.format(
        repo=repo,
        data_ref=data_ref,
        ros_distro=quote(ros_distro, safe=""),
        package=quote(package, safe=""),
    )
    text = _fetch_text(url, timeout=timeout, not_found_ok=True)
    if text is None:
        return None
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return None
    try:
        record = json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise RegistryError(
            f"invalid history record for {package!r} (last line of {url}): {exc}"
        ) from exc
    if not isinstance(record, dict):
        raise RegistryError(
            f"history record for {package!r} is not a JSON object"
        )
    return record
