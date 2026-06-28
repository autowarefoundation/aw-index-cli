"""Load Autoware Index distribution YAML from a local path or the registry."""

from __future__ import annotations

import urllib.error
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

import yaml

DEFAULT_REPO = "autowarefoundation/autoware-index"
DEFAULT_REF = "main"
RAW_URL = "https://raw.githubusercontent.com/{repo}/{ref}/distributions/{ros_distro}.yaml"
SUPPORTED_SCHEMA_VERSION = "2"


class RegistryError(Exception):
    """Raised when a distribution cannot be located, fetched, or parsed."""


def _fetch_text(url: str, *, timeout: float, not_found_ok: bool = False) -> str | None:
    """Fetch ``url`` and decode UTF-8, mapping failures to :class:`RegistryError`.

    When ``not_found_ok`` is true an HTTP 404 returns ``None`` instead of raising
    — used to treat a missing per-package history file as "no records yet".
    """
    try:
        with urlopen(url, timeout=timeout) as response:
            return response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        if not_found_ok and exc.code == 404:
            return None
        raise RegistryError(
            f"could not fetch {url}: HTTP {exc.code} {exc.reason}"
        ) from exc
    except TimeoutError as exc:
        raise RegistryError(f"timed out fetching {url} after {timeout}s") from exc
    except urllib.error.URLError as exc:
        raise RegistryError(f"could not fetch {url}: {exc.reason}") from exc
    except UnicodeDecodeError as exc:
        raise RegistryError(
            f"response from {url} was not valid UTF-8: {exc}"
        ) from exc


def _distribution_file(path: Path, ros_distro: str) -> Path:
    """Resolve the YAML file for ``ros_distro`` given a file or directory path."""
    if path.is_file():
        return path
    if path.is_dir():
        return path / "distributions" / f"{ros_distro}.yaml"
    # Path may be a file that does not exist; surface a clear error.
    raise RegistryError(f"registry path does not exist: {path}")


def load_distribution(
    ros_distro: str,
    *,
    path: str | Path | None = None,
    repo: str = DEFAULT_REPO,
    ref: str = DEFAULT_REF,
    timeout: float = 30,
) -> dict:
    """Load and validate the distribution YAML for ``ros_distro``.

    If ``path`` is given it is read locally (a file directly, or a directory in
    which ``distributions/<ros_distro>.yaml`` is expected). Otherwise the file is
    fetched from raw.githubusercontent.com for ``repo`` at ``ref``.

    Only documents with ``schema_version`` equal to
    :data:`SUPPORTED_SCHEMA_VERSION` are accepted; anything else raises
    :class:`RegistryError` rather than ever producing silent empty output.
    """
    if path is not None:
        target = _distribution_file(Path(path), ros_distro)
        if not target.is_file():
            raise RegistryError(f"distribution file not found: {target}")
        try:
            raw = target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise RegistryError(f"could not read {target}: {exc}") from exc
    else:
        url = RAW_URL.format(repo=repo, ref=ref, ros_distro=quote(ros_distro, safe=""))
        raw = _fetch_text(url, timeout=timeout)

    try:
        parsed = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise RegistryError(f"invalid YAML for {ros_distro}: {exc}") from exc

    if not isinstance(parsed, dict):
        raise RegistryError(
            f"distribution for {ros_distro} is not a mapping"
        )
    schema_version = parsed.get("schema_version")
    if schema_version != SUPPORTED_SCHEMA_VERSION:
        raise RegistryError(
            f"distribution for {ros_distro} has schema_version "
            f"{schema_version!r}, which is not supported by this aw-index-cli "
            f"(supports: {SUPPORTED_SCHEMA_VERSION!r})"
        )
    if parsed.get("ros_distro") != ros_distro:
        raise RegistryError(
            f"ros_distro mismatch: expected {ros_distro!r}, "
            f"got {parsed.get('ros_distro')!r}"
        )
    repositories = parsed.get("repositories")
    if repositories is not None and not isinstance(repositories, dict):
        raise RegistryError(
            f"distribution for {ros_distro}: 'repositories' must be a mapping "
            f"of repository key to spec, got {type(repositories).__name__}"
        )
    for key, spec in (repositories or {}).items():
        if not isinstance(spec, dict):
            raise RegistryError(
                f"distribution for {ros_distro}: repository {key!r} must be "
                f"a mapping, got {type(spec).__name__}"
            )
    return parsed


def describe_source(
    *,
    path: str | Path | None = None,
    repo: str | None = None,
    ref: str | None = None,
) -> str:
    """Return a human-readable provenance string for the distribution source."""
    if path is not None:
        return f"local path {path}"
    return f"{repo or DEFAULT_REPO}@{ref or DEFAULT_REF}"
