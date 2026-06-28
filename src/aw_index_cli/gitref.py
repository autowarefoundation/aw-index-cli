"""Best-effort resolution of a remote git ref to a commit SHA."""

from __future__ import annotations

import subprocess


def remote_sha(url: str, ref_value: str, *, timeout: float = 10) -> str | None:
    """Return the commit SHA that ``ref_value`` resolves to in remote ``url``.

    Uses ``git ls-remote``. Best-effort: returns ``None`` if git is missing, the
    command fails or times out, or the ref is not found — it never raises, so a
    caller can treat an unavailable answer as "unknown".
    """
    try:
        proc = subprocess.run(
            ["git", "ls-remote", url, ref_value],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    lines = proc.stdout.strip().splitlines()
    if not lines:
        return None
    sha = lines[0].split("\t", 1)[0].strip()
    return sha or None
