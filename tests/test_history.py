"""Tests for aw_index_cli.history."""

from __future__ import annotations

import io
import urllib.error

import pytest

from aw_index_cli import history
from aw_index_cli import registry
from aw_index_cli.history import latest_record
from aw_index_cli.registry import RegistryError


class _Resp:
    def __init__(self, data: bytes):
        self._buf = io.BytesIO(data)

    def read(self):
        return self._buf.read()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _patch(monkeypatch, fn):
    monkeypatch.setattr(registry, "urlopen", fn)


def test_latest_record_returns_last_line(monkeypatch):
    ndjson = (
        '{"status":"pass","autoware_version":"1.7.0","at":"2026-05-12T06:00:00Z"}\n'
        '{"schema":2,"status":"fail","autoware_version":"1.9.0",'
        '"at":"2026-05-30T06:00:00Z","resolved_sha":"abc"}\n'
    )
    _patch(monkeypatch, lambda url, timeout=None: _Resp(ndjson.encode()))
    record = latest_record("pkg", ros_distro="jazzy")
    assert record["status"] == "fail"
    assert record["autoware_version"] == "1.9.0"


def test_latest_record_handles_v1_last_line(monkeypatch):
    ndjson = '{"status":"pass","autoware_version":"1.7.0","at":"2026-05-12T06:00:00Z"}\n'
    _patch(monkeypatch, lambda url, timeout=None: _Resp(ndjson.encode()))
    record = latest_record("pkg", ros_distro="jazzy")
    assert record["status"] == "pass"
    assert "schema" not in record


def test_latest_record_404_returns_none(monkeypatch):
    def raise_404(url, timeout=None):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    _patch(monkeypatch, raise_404)
    assert latest_record("pkg", ros_distro="jazzy") is None


def test_latest_record_empty_returns_none(monkeypatch):
    _patch(monkeypatch, lambda url, timeout=None: _Resp(b"\n  \n"))
    assert latest_record("pkg", ros_distro="jazzy") is None


def test_latest_record_other_http_error_raises(monkeypatch):
    def raise_500(url, timeout=None):
        raise urllib.error.HTTPError(url, 500, "Server Error", {}, None)

    _patch(monkeypatch, raise_500)
    with pytest.raises(RegistryError):
        latest_record("pkg", ros_distro="jazzy")


def test_latest_record_bad_json_raises(monkeypatch):
    _patch(monkeypatch, lambda url, timeout=None: _Resp(b"{not valid json}\n"))
    with pytest.raises(RegistryError):
        latest_record("pkg", ros_distro="jazzy")


def test_latest_record_url_shape(monkeypatch):
    captured = {}

    def capture(url, timeout=None):
        captured["url"] = url
        return _Resp(b'{"status":"pass"}\n')

    _patch(monkeypatch, capture)
    latest_record("my_pkg", ros_distro="humble", repo="me/idx", data_ref="data")
    assert captured["url"] == (
        "https://raw.githubusercontent.com/me/idx/data/history/humble/my_pkg.ndjson"
    )


def test_latest_record_encodes_path_segments(monkeypatch):
    captured = {}

    def capture(url, timeout=None):
        captured["url"] = url
        return _Resp(b'{"status":"pass"}\n')

    _patch(monkeypatch, capture)
    # URL-special chars in distro/package are percent-encoded to single segments;
    # the repo "owner/name" slash is preserved.
    latest_record("a/b", ros_distro="x?y", repo="me/idx")
    assert "/me/idx/data/history/x%3Fy/a%2Fb.ndjson" in captured["url"]
