"""Tests for aw_index_cli.registry."""

from __future__ import annotations

import io
import urllib.error

import yaml
import pytest

from aw_index_cli import registry
from aw_index_cli.registry import (
    RegistryError,
    describe_source,
    load_distribution,
)


def test_load_from_directory(distributions_dir, sample_distribution):
    result = load_distribution("jazzy", path=distributions_dir)
    assert result == sample_distribution


def test_load_from_file(distributions_dir, sample_distribution):
    file_path = distributions_dir / "distributions" / "jazzy.yaml"
    result = load_distribution("jazzy", path=file_path)
    assert result["ros_distro"] == "jazzy"
    assert "alpha-mono" in result["repositories"]


def test_missing_file_raises(tmp_path):
    with pytest.raises(RegistryError, match="not found|does not exist"):
        load_distribution("jazzy", path=tmp_path)


def test_missing_explicit_file_raises(tmp_path):
    with pytest.raises(RegistryError):
        load_distribution("jazzy", path=tmp_path / "nope.yaml")


def test_ros_distro_mismatch_raises(tmp_path):
    dist_dir = tmp_path / "distributions"
    dist_dir.mkdir()
    (dist_dir / "jazzy.yaml").write_text(
        yaml.safe_dump(
            {"schema_version": "2", "ros_distro": "humble", "repositories": {}}
        ),
        encoding="utf-8",
    )
    with pytest.raises(RegistryError, match="mismatch"):
        load_distribution("jazzy", path=tmp_path)


def test_unsupported_schema_version_raises(tmp_path):
    f = tmp_path / "jazzy.yaml"
    f.write_text(
        yaml.safe_dump(
            {"schema_version": "1", "ros_distro": "jazzy", "packages": {}}
        ),
        encoding="utf-8",
    )
    with pytest.raises(RegistryError) as excinfo:
        load_distribution("jazzy", path=f)
    message = str(excinfo.value)
    assert "'1'" in message
    assert "not supported by this aw-index-cli" in message
    assert "(supports: '2')" in message
    # The document may be older than the CLI; never advise upgrading it.
    assert "upgrade" not in message


def test_missing_schema_version_raises(tmp_path):
    f = tmp_path / "jazzy.yaml"
    f.write_text(
        yaml.safe_dump({"ros_distro": "jazzy", "repositories": {}}),
        encoding="utf-8",
    )
    with pytest.raises(RegistryError) as excinfo:
        load_distribution("jazzy", path=f)
    message = str(excinfo.value)
    assert "None" in message
    assert "not supported by this aw-index-cli" in message
    assert "(supports: '2')" in message


def test_non_mapping_raises(tmp_path):
    f = tmp_path / "jazzy.yaml"
    f.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(RegistryError, match="not a mapping"):
        load_distribution("jazzy", path=f)


def test_repositories_list_raises(tmp_path):
    f = tmp_path / "jazzy.yaml"
    f.write_text(
        yaml.safe_dump(
            {
                "schema_version": "2",
                "ros_distro": "jazzy",
                "repositories": ["alpha-mono", "mid-repo"],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(
        RegistryError, match="'repositories' must be a mapping"
    ) as excinfo:
        load_distribution("jazzy", path=f)
    assert "got list" in str(excinfo.value)


def test_repository_entry_string_raises(tmp_path):
    f = tmp_path / "jazzy.yaml"
    f.write_text(
        yaml.safe_dump(
            {
                "schema_version": "2",
                "ros_distro": "jazzy",
                "repositories": {"alpha-mono": "https://x/alpha_mono"},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(
        RegistryError, match="repository 'alpha-mono' must be a mapping"
    ) as excinfo:
        load_distribution("jazzy", path=f)
    assert "got str" in str(excinfo.value)


def test_repository_entry_null_raises(tmp_path):
    f = tmp_path / "jazzy.yaml"
    f.write_text(
        "schema_version: '2'\nros_distro: jazzy\nrepositories:\n  bare-repo:\n",
        encoding="utf-8",
    )
    with pytest.raises(
        RegistryError, match="repository 'bare-repo' must be a mapping"
    ):
        load_distribution("jazzy", path=f)


class _FakeResponse:
    def __init__(self, data: bytes):
        self._buf = io.BytesIO(data)

    def read(self):
        return self._buf.read()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_fetch_success_monkeypatched(monkeypatch, sample_distribution):
    payload = yaml.safe_dump(sample_distribution).encode("utf-8")
    captured = {}

    def fake_urlopen(url, timeout=None):
        captured["url"] = url
        captured["timeout"] = timeout
        return _FakeResponse(payload)

    monkeypatch.setattr(registry, "urlopen", fake_urlopen)
    result = load_distribution("jazzy")
    assert result == sample_distribution
    assert captured["url"] == (
        "https://raw.githubusercontent.com/autowarefoundation/"
        "autoware-index/main/distributions/jazzy.yaml"
    )


def test_fetch_url_encodes_rosdistro(monkeypatch, sample_distribution):
    captured = {}

    def fake_urlopen(url, timeout=None):
        captured["url"] = url
        return _FakeResponse(yaml.safe_dump(sample_distribution).encode("utf-8"))

    monkeypatch.setattr(registry, "urlopen", fake_urlopen)
    # A distro with URL-special characters must be percent-encoded into a single
    # path segment (it later fails the ros_distro match, but the URL is built first).
    with pytest.raises(RegistryError):
        load_distribution("ros?inject")
    assert "/distributions/ros%3Finject.yaml" in captured["url"]


def test_fetch_custom_repo_ref(monkeypatch, sample_distribution):
    payload = yaml.safe_dump(sample_distribution).encode("utf-8")
    captured = {}

    def fake_urlopen(url, timeout=None):
        captured["url"] = url
        return _FakeResponse(payload)

    monkeypatch.setattr(registry, "urlopen", fake_urlopen)
    load_distribution("jazzy", repo="me/fork", ref="dev")
    assert "me/fork/dev/distributions/jazzy.yaml" in captured["url"]


def test_fetch_http_error_raises(monkeypatch):
    def fake_urlopen(url, timeout=None):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    monkeypatch.setattr(registry, "urlopen", fake_urlopen)
    with pytest.raises(RegistryError, match="404"):
        load_distribution("jazzy")


def test_fetch_url_error_raises(monkeypatch):
    def fake_urlopen(url, timeout=None):
        raise urllib.error.URLError("name resolution failed")

    monkeypatch.setattr(registry, "urlopen", fake_urlopen)
    with pytest.raises(RegistryError, match="could not fetch"):
        load_distribution("jazzy")


def test_malformed_yaml_raises(tmp_path):
    f = tmp_path / "jazzy.yaml"
    f.write_text("key: : : bad\n  - nope\n", encoding="utf-8")
    with pytest.raises(RegistryError, match="invalid YAML"):
        load_distribution("jazzy", path=f)


def test_fetch_timeout_raises(monkeypatch):
    def fake_urlopen(url, timeout=None):
        raise TimeoutError("timed out")

    monkeypatch.setattr(registry, "urlopen", fake_urlopen)
    with pytest.raises(RegistryError, match="timed out"):
        load_distribution("jazzy")


def test_fetch_non_utf8_body_raises(monkeypatch):
    def fake_urlopen(url, timeout=None):
        return _FakeResponse(b"\xff\xfe\x00bad")

    monkeypatch.setattr(registry, "urlopen", fake_urlopen)
    with pytest.raises(RegistryError, match="UTF-8"):
        load_distribution("jazzy")


def test_select_among_two_distros(tmp_path):
    dist_dir = tmp_path / "distributions"
    dist_dir.mkdir()
    (dist_dir / "jazzy.yaml").write_text(
        yaml.safe_dump(
            {"schema_version": "2", "ros_distro": "jazzy", "repositories": {}}
        ),
        encoding="utf-8",
    )
    (dist_dir / "humble.yaml").write_text(
        yaml.safe_dump(
            {"schema_version": "2", "ros_distro": "humble", "repositories": {}}
        ),
        encoding="utf-8",
    )
    assert load_distribution("jazzy", path=tmp_path)["ros_distro"] == "jazzy"
    assert load_distribution("humble", path=tmp_path)["ros_distro"] == "humble"


def test_absent_distro_raises_not_found(tmp_path):
    dist_dir = tmp_path / "distributions"
    dist_dir.mkdir()
    (dist_dir / "jazzy.yaml").write_text(
        yaml.safe_dump(
            {"schema_version": "2", "ros_distro": "jazzy", "repositories": {}}
        ),
        encoding="utf-8",
    )
    with pytest.raises(RegistryError, match="not found"):
        load_distribution("humble", path=tmp_path)


def test_describe_source_local():
    assert describe_source(path="/x/jazzy.yaml") == "local path /x/jazzy.yaml"


def test_describe_source_path_wins_over_repo_ref():
    assert describe_source(path="/x", repo="a/b", ref="dev") == "local path /x"


def test_describe_source_remote():
    assert describe_source(repo="a/b", ref="main") == "a/b@main"


def test_describe_source_remote_defaults():
    assert describe_source() == "autowarefoundation/autoware-index@main"
