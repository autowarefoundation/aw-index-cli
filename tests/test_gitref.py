"""Tests for aw_index_cli.gitref."""

from __future__ import annotations

import subprocess

from aw_index_cli import gitref
from aw_index_cli.gitref import remote_sha


def _completed(returncode: int, stdout: str) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(["git"], returncode, stdout=stdout, stderr="")


def test_remote_sha_parses_first_column(monkeypatch):
    out = "deadbeefcafe\trefs/heads/main\n"
    monkeypatch.setattr(gitref.subprocess, "run", lambda *a, **k: _completed(0, out))
    assert remote_sha("https://x/y", "main") == "deadbeefcafe"


def test_remote_sha_nonzero_returns_none(monkeypatch):
    monkeypatch.setattr(gitref.subprocess, "run", lambda *a, **k: _completed(2, ""))
    assert remote_sha("https://x/y", "main") is None


def test_remote_sha_empty_output_returns_none(monkeypatch):
    monkeypatch.setattr(gitref.subprocess, "run", lambda *a, **k: _completed(0, ""))
    assert remote_sha("https://x/y", "main") is None


def test_remote_sha_git_missing_returns_none(monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError("git")

    monkeypatch.setattr(gitref.subprocess, "run", boom)
    assert remote_sha("https://x/y", "main") is None


def test_remote_sha_timeout_returns_none(monkeypatch):
    def boom(*a, **k):
        raise subprocess.TimeoutExpired(["git"], 10)

    monkeypatch.setattr(gitref.subprocess, "run", boom)
    assert remote_sha("https://x/y", "main") is None
