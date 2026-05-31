"""Shared fixtures for aw-index-cli tests."""

from __future__ import annotations

import yaml
import pytest


@pytest.fixture
def sample_distribution() -> dict:
    """A small but representative jazzy distribution dict.

    Covers a branch ref, a tag ref, and a sha ref, plus varied tags so tag
    filtering can be exercised. Packages are intentionally out of sorted order.
    """
    return {
        "schema_version": "1",
        "ros_distro": "jazzy",
        "packages": {
            "zeta_pkg": {
                "repository": "https://github.com/example/zeta_pkg",
                "description": "A sha-pinned package.",
                "governance": "community",
                "tags": ["perception"],
                "ref": {"kind": "sha", "value": "a" * 40},
            },
            "alpha_pkg": {
                "repository": "https://github.com/example/alpha_pkg",
                "description": "A branch-pinned package.",
                "governance": "foundation",
                "tags": ["sensing", "perception"],
                "ref": {"kind": "branch", "value": "main"},
            },
            "mid_pkg": {
                "repository": "https://github.com/example/mid_pkg",
                "governance": "community",
                "tags": ["planning"],
                "ref": {"kind": "tag", "value": "v1.2.3"},
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
