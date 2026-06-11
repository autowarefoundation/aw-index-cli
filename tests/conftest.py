"""Shared fixtures for aw-index-cli tests."""

from __future__ import annotations

import yaml
import pytest


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
