"""Tests for aw_index_cli.compose."""

from __future__ import annotations

import yaml
import pytest

from aw_index_cli.compose import (
    ComposeError,
    provenance_header,
    render_repos,
    select_repositories,
    to_repos_entries,
)


def test_select_no_tags_returns_all_sorted(sample_distribution):
    keys = [key for key, _, _ in select_repositories(sample_distribution)]
    assert keys == ["alpha-mono", "mid-repo", "zeta-stack"]


def test_select_no_tags_lists_all_packages_sorted(sample_distribution):
    selection = select_repositories(sample_distribution)
    by_key = {key: names for key, _, names in selection}
    assert by_key == {
        "alpha-mono": ["alpha_perception", "alpha_sensing"],
        "mid-repo": ["mid_pkg"],
        "zeta-stack": ["zeta_pkg"],
    }


def test_select_empty_tags_returns_all(sample_distribution):
    keys = [key for key, _, _ in select_repositories(sample_distribution, tags=[])]
    assert keys == ["alpha-mono", "mid-repo", "zeta-stack"]


def test_select_tag_intersection(sample_distribution):
    selection = select_repositories(sample_distribution, tags=["perception"])
    assert [(key, names) for key, _, names in selection] == [
        ("alpha-mono", ["alpha_perception"]),
        ("zeta-stack", ["zeta_pkg"]),
    ]


def test_select_monorepo_partial_package_selection(sample_distribution):
    # Only one of the monorepo's two packages matches; the repository is still
    # selected, and the selection names only the matching package.
    selection = select_repositories(sample_distribution, tags=["sensing"])
    assert [(key, names) for key, _, names in selection] == [
        ("alpha-mono", ["alpha_sensing"]),
    ]


def test_select_tag_no_match_is_empty(sample_distribution):
    assert select_repositories(sample_distribution, tags=["nonexistent"]) == []


def test_select_missing_repositories_key():
    assert select_repositories({"ros_distro": "jazzy"}) == []


def test_select_excludes_empty_and_missing_tags_under_filter():
    distribution = {
        "ros_distro": "jazzy",
        "repositories": {
            "edge-repo": {
                "url": "https://x/edge",
                "ref": {"value": "main"},
                "packages": {
                    "empty_tags": {"tags": []},
                    "no_tags": {},
                },
            },
        },
    }
    # Under a tag filter, neither package matches, so the repo drops out.
    assert select_repositories(distribution, tags=["sensing"]) == []
    # With tags=None every package is selected.
    selection = select_repositories(distribution, tags=None)
    assert [(key, names) for key, _, names in selection] == [
        ("edge-repo", ["empty_tags", "no_tags"]),
    ]


def test_select_none_package_spec_retained_unfiltered_excluded_when_filtered():
    distribution = {
        "ros_distro": "jazzy",
        "repositories": {
            "r": {
                "url": "https://x/r",
                "ref": {"value": "main"},
                "packages": {"p": None},
            },
        },
    }
    # Retained when unfiltered.
    selection = select_repositories(distribution, tags=None)
    assert [(key, names) for key, _, names in selection] == [("r", ["p"])]
    # Excluded when a tag filter is applied.
    assert select_repositories(distribution, tags=["sensing"]) == []


def test_select_repo_without_packages_is_excluded():
    distribution = {
        "ros_distro": "jazzy",
        "repositories": {
            "bare-repo": {"url": "https://x/bare", "ref": {"value": "main"}},
        },
    }
    assert select_repositories(distribution) == []
    assert select_repositories(distribution, tags=["sensing"]) == []


def test_to_repos_entries_field_mapping(sample_distribution):
    repositories = select_repositories(sample_distribution)
    entries = to_repos_entries(repositories)
    # Order preserved (sorted by repository key).
    assert list(entries) == ["alpha-mono", "mid-repo", "zeta-stack"]
    # branch ref + monorepo packages manifest
    assert entries["alpha-mono"] == {
        "type": "git",
        "url": "https://github.com/example/alpha_mono",
        "version": "main",
        "packages": ["alpha_perception", "alpha_sensing"],
    }
    # tag ref
    assert entries["mid-repo"]["version"] == "v1.2.3"
    # sha ref
    assert entries["zeta-stack"]["version"] == "a" * 40
    assert entries["zeta-stack"]["type"] == "git"


def test_to_repos_entries_key_is_registry_repo_key_not_url_basename():
    entries = to_repos_entries(
        [
            (
                "my-stack",
                {
                    "url": "https://x/y/something_else.git",
                    "ref": {"value": "main"},
                },
                ["pkg_a"],
            ),
        ]
    )
    assert list(entries) == ["my-stack"]
    assert entries["my-stack"]["url"] == "https://x/y/something_else.git"


def test_to_repos_entries_packages_manifest_only_selected():
    entries = to_repos_entries(
        [
            (
                "mono",
                {"url": "https://x/mono", "ref": {"value": "main"}},
                ["pkg_b"],
            ),
        ]
    )
    # The entry is emitted even though only one of the repo's packages was
    # selected, and the manifest names only that one.
    assert entries["mono"]["packages"] == ["pkg_b"]


def test_to_repos_entries_missing_url_raises():
    with pytest.raises(ComposeError, match="url"):
        to_repos_entries([("r", {"ref": {"value": "main"}}, ["p"])])


def test_to_repos_entries_missing_ref_value_raises():
    with pytest.raises(ComposeError, match="ref.value"):
        to_repos_entries([("r", {"url": "https://x/r"}, ["p"])])


def test_to_repos_entries_none_spec_raises_url():
    with pytest.raises(ComposeError, match="url"):
        to_repos_entries([("r", None, ["p"])])


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


def test_provenance_header_selection_lists_packages_per_entry():
    lines = provenance_header(
        tool_version="0.1.0",
        ros_distro="jazzy",
        source="src",
        selection=[
            ("alpha-mono", ["alpha_perception", "alpha_sensing"]),
            ("mid-repo", ["mid_pkg"]),
        ],
    )
    assert all(line.startswith("#") for line in lines)
    assert "# selected packages by repository:" in lines
    assert "#   alpha-mono: alpha_perception, alpha_sensing" in lines
    assert "#   mid-repo: mid_pkg" in lines


def test_provenance_header_selection_omitted_when_empty():
    for selection in (None, []):
        lines = provenance_header(
            tool_version="0.1.0",
            ros_distro="jazzy",
            source="src",
            selection=selection,
        )
        assert not any("selected packages" in line for line in lines)


def test_render_repos_valid_yaml_roundtrip(sample_distribution):
    header = provenance_header(
        tool_version="0.1.0", ros_distro="jazzy", source="src"
    )
    text = render_repos(sample_distribution, header_lines=header)
    parsed = yaml.safe_load(text)
    assert parsed["repositories"]["alpha-mono"] == {
        "type": "git",
        "url": "https://github.com/example/alpha_mono",
        "version": "main",
        "packages": ["alpha_perception", "alpha_sensing"],
    }
    assert list(parsed["repositories"]) == ["alpha-mono", "mid-repo", "zeta-stack"]


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
    assert list(parsed["repositories"]) == ["mid-repo"]
    assert parsed["repositories"]["mid-repo"]["packages"] == ["mid_pkg"]


def test_render_repos_monorepo_partial_selection(sample_distribution):
    header = provenance_header(
        tool_version="0.1.0", ros_distro="jazzy", source="src", tags=["sensing"]
    )
    text = render_repos(sample_distribution, tags=["sensing"], header_lines=header)
    parsed = yaml.safe_load(text)
    # The monorepo entry is still emitted, with only the selected package in
    # its manifest.
    assert list(parsed["repositories"]) == ["alpha-mono"]
    assert parsed["repositories"]["alpha-mono"]["packages"] == ["alpha_sensing"]


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


def test_render_repos_empty_distribution():
    header = provenance_header(
        tool_version="0.1.0", ros_distro="jazzy", source="src"
    )
    text = render_repos(
        {"ros_distro": "jazzy", "repositories": {}}, header_lines=header
    )
    parsed = yaml.safe_load(text)
    assert parsed == {"repositories": {}}
