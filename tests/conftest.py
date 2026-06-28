"""Shared fixtures for aw-index-cli tests."""

from __future__ import annotations

import io
import urllib.error

import yaml
import pytest


class _FakeResponse:
    """Minimal urlopen() stand-in wrapping fixed bytes."""

    def __init__(self, data: bytes):
        self._buf = io.BytesIO(data)

    def read(self):
        return self._buf.read()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def sample_distribution() -> dict:
    """A small but representative schema_version "2" jazzy distribution dict.

    Covers a branch ref, a tag ref, and a sha ref; a monorepo with two
    packages plus two single-package repositories; and varied tags so tag
    filtering can be exercised. Repository keys are intentionally out of
    sorted order.
    """
    return {
        "schema_version": "2",
        "ros_distro": "jazzy",
        "repositories": {
            "zeta-stack": {
                "url": "https://github.com/example/zeta_stack",
                "ref": {"kind": "sha", "value": "a" * 40},
                "governance": "community",
                "maintainers": [
                    {
                        "name": "Zeta Dev",
                        "email": "zeta@example.com",
                        "github": "zetadev",
                    }
                ],
                "packages": {
                    "zeta_pkg": {
                        "tags": ["perception"],
                        "description": "A sha-pinned package.",
                    },
                },
            },
            "alpha-mono": {
                "url": "https://github.com/example/alpha_mono",
                "ref": {"kind": "branch", "value": "main"},
                "governance": "foundation",
                "maintainers": [
                    {
                        "name": "Alpha Dev",
                        "email": "alpha@example.com",
                        "github": "alphadev",
                    }
                ],
                "packages": {
                    "alpha_sensing": {
                        "tags": ["sensing"],
                        "description": "Sensing half of the monorepo.",
                    },
                    "alpha_perception": {
                        "tags": ["perception"],
                        "maintainers": [
                            {
                                "name": "Percy Dev",
                                "email": "percy@example.com",
                                "github": "percydev",
                            }
                        ],
                    },
                },
            },
            "mid-repo": {
                "url": "https://github.com/example/mid_repo",
                "ref": {"kind": "tag", "value": "v1.2.3"},
                "governance": "community",
                "packages": {
                    "mid_pkg": {"tags": ["planning"]},
                },
            },
        },
    }


@pytest.fixture
def distributions_dir(tmp_path, sample_distribution):
    """A temp registry directory holding ``distributions/jazzy.yaml``."""
    dist_dir = tmp_path / "distributions"
    dist_dir.mkdir()
    (dist_dir / "jazzy.yaml").write_text(
        yaml.safe_dump(sample_distribution, sort_keys=False),
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def sample_repos_text(sample_distribution) -> str:
    """A real composed ``.repos`` for ``sample_distribution`` (header + body).

    Generated through the actual compose functions so it always matches what the
    CLI emits — including the ``# rosdistro:`` line and the
    ``# selected packages by repository:`` block that ``check`` parses.
    """
    from aw_index_cli.compose import (
        provenance_header,
        render_repos,
        select_repositories,
    )

    selection = [
        (key, names) for key, _spec, names in select_repositories(sample_distribution)
    ]
    header = provenance_header(
        tool_version="0.1.0",
        ros_distro="jazzy",
        source="src",
        selection=selection,
    )
    return render_repos(sample_distribution, header_lines=header)


@pytest.fixture
def history_urlopen():
    """Factory: ``{package: ndjson_text}`` → a urlopen routing history by URL.

    Any history URL whose package is in the mapping returns that NDJSON; anything
    else raises HTTP 404 (so unmapped packages read as "no records yet").
    """

    def factory(records: dict[str, str]):
        def _urlopen(url, timeout=None):
            if "/history/" in url and url.endswith(".ndjson"):
                package = url.rsplit("/", 1)[-1][: -len(".ndjson")]
                if package in records:
                    return _FakeResponse(records[package].encode("utf-8"))
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

        return _urlopen

    return factory
