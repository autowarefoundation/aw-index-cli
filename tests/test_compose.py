"""Tests for aw_index_cli.compose."""

from __future__ import annotations

import yaml
import pytest

from aw_index_cli.compose import (
    ComposeError,
    provenance_header,
    render_repos,
    select_packages,
    to_repos_entries,
)


def test_select_no_tags_returns_all_sorted(sample_distribution):
    names = [name for name, _ in select_packages(sample_distribution)]
    assert names == ["alpha_pkg", "mid_pkg", "zeta_pkg"]


def test_select_empty_tags_returns_all(sample_distribution):
    names = [name for name, _ in select_packages(sample_distribution, tags=[])]
    assert names == ["alpha_pkg", "mid_pkg", "zeta_pkg"]


def test_select_tag_intersection(sample_distribution):
    names = [
        name for name, _ in select_packages(sample_distribution, tags=["perception"])
    ]
    assert names == ["alpha_pkg", "zeta_pkg"]


def test_select_tag_no_match_is_empty(sample_distribution):
    assert select_packages(sample_distribution, tags=["nonexistent"]) == []


def test_select_missing_packages_key():
    assert select_packages({"ros_distro": "jazzy"}) == []


def test_to_repos_entries_field_mapping(sample_distribution):
    packages = select_packages(sample_distribution)
    entries = to_repos_entries(packages)
    # Order preserved (sorted by name).
    assert list(entries) == ["alpha_pkg", "mid_pkg", "zeta_pkg"]
    # branch ref
    assert entries["alpha_pkg"] == {
        "type": "git",
        "url": "https://github.com/example/alpha_pkg",
        "version": "main",
    }
    # tag ref
    assert entries["mid_pkg"]["version"] == "v1.2.3"
    # sha ref
    assert entries["zeta_pkg"]["version"] == "a" * 40
    assert entries["zeta_pkg"]["type"] == "git"


def test_to_repos_entries_missing_repository_raises():
    with pytest.raises(ComposeError, match="repository"):
        to_repos_entries([("p", {"ref": {"value": "main"}})])


def test_to_repos_entries_missing_ref_value_raises():
    with pytest.raises(ComposeError, match="ref.value"):
        to_repos_entries([("p", {"repository": "https://x/p"})])


def test_to_repos_entries_none_spec_raises_repository():
    with pytest.raises(ComposeError, match="repository"):
        to_repos_entries([("p", None)])


def test_to_repos_entries_path_key_is_repo_basename():
    entries = to_repos_entries(
        [
            ("a", {"repository": "https://x/y/foo.git", "ref": {"value": "main"}}),
            ("b", {"repository": "https://x/y/bar/", "ref": {"value": "dev"}}),
        ]
    )
    assert list(entries) == ["bar", "foo"]
    assert entries["foo"]["url"] == "https://x/y/foo.git"
    assert entries["bar"]["url"] == "https://x/y/bar/"


def test_to_repos_entries_dedup_same_url_same_ref():
    entries = to_repos_entries(
        [
            ("pkg_a", {"repository": "https://x/y/mono", "ref": {"value": "main"}}),
            ("pkg_b", {"repository": "https://x/y/mono", "ref": {"value": "main"}}),
        ]
    )
    assert list(entries) == ["mono"]
    assert entries["mono"] == {
        "type": "git",
        "url": "https://x/y/mono",
        "version": "main",
    }


def test_to_repos_entries_same_url_different_ref_raises():
    with pytest.raises(ComposeError, match="different refs"):
        to_repos_entries(
            [
                ("pkg_a", {"repository": "https://x/y/mono", "ref": {"value": "main"}}),
                ("pkg_b", {"repository": "https://x/y/mono", "ref": {"value": "dev"}}),
            ]
        )


def test_provenance_header_lines_start_with_hash():
    lines = provenance_header(
        tool_version="0.1.0",
        ros_distro="jazzy",
        source="local path /x",
    )
    assert all(line.startswith("#") for line in lines)
    assert any("aw-index-cli 0.1.0" in line for line in lines)
    assert any("rosdistro: jazzy" in line for line in lines)
    assert any("tags: all" in line for line in lines)
    assert lines[-1].startswith("# Generated file")


def test_provenance_header_tags_rendered():
    lines = provenance_header(
        tool_version="0.1.0",
        ros_distro="jazzy",
        source="src",
        tags=["sensing", "perception"],
    )
    assert any("tags: sensing, perception" in line for line in lines)


def test_provenance_header_autoware_only_when_given():
    without = provenance_header(
        tool_version="0.1.0", ros_distro="jazzy", source="src"
    )
    assert not any("autoware" in line for line in without)
    with_aw = provenance_header(
        tool_version="0.1.0", ros_distro="jazzy", source="src", autoware="2025.02"
    )
    aw_line = [line for line in with_aw if "autoware: 2025.02" in line]
    assert aw_line and "informational" in aw_line[0]


def test_provenance_header_generated_at_optional():
    without = provenance_header(
        tool_version="0.1.0", ros_distro="jazzy", source="src"
    )
    assert not any("generated_at" in line for line in without)
    with_ts = provenance_header(
        tool_version="0.1.0",
        ros_distro="jazzy",
        source="src",
        generated_at="2026-05-31T00:00:00+00:00",
    )
    assert any("generated_at: 2026-05-31T00:00:00+00:00" in line for line in with_ts)


def test_render_repos_valid_yaml_roundtrip(sample_distribution):
    header = provenance_header(
        tool_version="0.1.0", ros_distro="jazzy", source="src"
    )
    text = render_repos(sample_distribution, header_lines=header)
    parsed = yaml.safe_load(text)
    assert parsed["repositories"]["alpha_pkg"] == {
        "type": "git",
        "url": "https://github.com/example/alpha_pkg",
        "version": "main",
    }
    assert list(parsed["repositories"]) == ["alpha_pkg", "mid_pkg", "zeta_pkg"]


def test_render_repos_deterministic_without_generated_at(sample_distribution):
    header = provenance_header(
        tool_version="0.1.0", ros_distro="jazzy", source="src"
    )
    first = render_repos(sample_distribution, header_lines=header)
    second = render_repos(sample_distribution, header_lines=header)
    assert first == second


def test_render_repos_empty_selection_valid(sample_distribution):
    header = provenance_header(
        tool_version="0.1.0", ros_distro="jazzy", source="src", tags=["none"]
    )
    text = render_repos(sample_distribution, tags=["none"], header_lines=header)
    parsed = yaml.safe_load(text)
    assert parsed == {"repositories": {}}
    assert "repositories: {}" in text


def test_render_repos_tag_filter(sample_distribution):
    header = provenance_header(
        tool_version="0.1.0", ros_distro="jazzy", source="src", tags=["planning"]
    )
    text = render_repos(sample_distribution, tags=["planning"], header_lines=header)
    parsed = yaml.safe_load(text)
    assert list(parsed["repositories"]) == ["mid_pkg"]


def test_render_repos_header_precedes_body_one_trailing_newline(sample_distribution):
    header = provenance_header(
        tool_version="0.1.0", ros_distro="jazzy", source="src"
    )
    text = render_repos(sample_distribution, header_lines=header)
    lines = text.split("\n")
    # The rendered text starts with the first header line.
    assert text.startswith(header[0])
    # Every header line precedes the YAML body, in order.
    assert lines[: len(header)] == header
    # The line immediately after the last header line is 'repositories:'.
    assert lines[len(header)] == "repositories:"
    # Ends with exactly one trailing newline.
    assert text.endswith("\n")
    assert not text.endswith("\n\n")


def test_select_excludes_empty_and_missing_tags_under_filter():
    distribution = {
        "ros_distro": "jazzy",
        "packages": {
            "empty_tags": {
                "repository": "https://x/empty",
                "tags": [],
                "ref": {"value": "main"},
            },
            "no_tags": {
                "repository": "https://x/none",
                "ref": {"value": "main"},
            },
        },
    }
    # Under a tag filter, both are excluded.
    assert select_packages(distribution, tags=["sensing"]) == []
    # With tags=None both are included.
    names = [name for name, _ in select_packages(distribution, tags=None)]
    assert names == ["empty_tags", "no_tags"]


def test_select_none_spec_retained_unfiltered_excluded_when_filtered():
    distribution = {"ros_distro": "jazzy", "packages": {"p": None}}
    # Retained when unfiltered.
    assert select_packages(distribution, tags=None) == [("p", None)]
    # Excluded when a tag filter is applied.
    assert select_packages(distribution, tags=["sensing"]) == []


def test_render_repos_empty_distribution(sample_distribution):
    header = provenance_header(
        tool_version="0.1.0", ros_distro="jazzy", source="src"
    )
    text = render_repos(
        {"ros_distro": "jazzy", "packages": {}}, header_lines=header
    )
    parsed = yaml.safe_load(text)
    assert parsed == {"repositories": {}}
