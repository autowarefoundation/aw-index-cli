"""Load Autoware Index distribution YAML from a local path or the registry."""

from __future__ import annotations

import urllib.error
from pathlib import Path
from urllib.request import urlopen

import yaml

DEFAULT_REPO = "autowarefoundation/autoware-index"
DEFAULT_REF = "main"
RAW_URL = "https://raw.githubusercontent.com/{repo}/{ref}/distributions/{ros_distro}.yaml"


class RegistryError(Exception):
    """Raised when a distribution cannot be located, fetched, or parsed."""


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
        url = RAW_URL.format(repo=repo, ref=ref, ros_distro=ros_distro)
        try:
            with urlopen(url, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
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

    try:
        parsed = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise RegistryError(f"invalid YAML for {ros_distro}: {exc}") from exc

    if not isinstance(parsed, dict):
        raise RegistryError(
            f"distribution for {ros_distro} is not a mapping"
        )
    if parsed.get("ros_distro") != ros_distro:
        raise RegistryError(
            f"ros_distro mismatch: expected {ros_distro!r}, "
            f"got {parsed.get('ros_distro')!r}"
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
