"""Tests for aw_index_cli.compose."""

from __future__ import annotations

import copy

import pytest
import yaml

from aw_index_cli.compose import ComposeError
from aw_index_cli.compose import provenance_header
from aw_index_cli.compose import render_repos
from aw_index_cli.compose import select_repositories
from aw_index_cli.compose import to_repos_entries
from aw_index_cli.compose import unknown_tags


def _selection_names(distribution: dict, **filters) -> list[tuple[str, list[str]]]:
    return [(key, names) for key, _spec, names in select_repositories(distribution, **filters)]


def test_v4_dependencies_expand_after_filters(dependent_distribution):
    expected = [
        ("app-repo", ["app_pkg", "same_repo_pkg"]),
        ("leaf-repo", ["leaf_pkg"]),
        ("mid-repo", ["mid_pkg"]),
    ]
    for filters in (
        {"packages": ["app_pkg"]},
        {"tags": ["planning"]},
        {"repository": ["app-repo"], "tags": ["planning"]},
    ):
        assert _selection_names(dependent_distribution, **filters) == expected


def test_v4_reference_design_filters_roots_before_dependency_expansion(
    dependent_distribution,
):
    dependent_distribution["repositories"]["app-repo"]["reference_design"] = True
    assert _selection_names(dependent_distribution, reference_design=True) == [
        ("app-repo", ["app_pkg", "same_repo_pkg"]),
        ("leaf-repo", ["leaf_pkg"]),
        ("mid-repo", ["mid_pkg"]),
    ]


def test_named_reference_design_list_is_rejected(sample_distribution):
    sample_distribution["repositories"]["alpha-mono"]["reference_design"] = ["pov"]
    with pytest.raises(ComposeError, match="reference_design.*not a boolean.*list"):
        select_repositories(sample_distribution, reference_design=True)


def test_v4_can_select_roots_only_for_list(dependent_distribution):
    assert _selection_names(
        dependent_distribution, packages=["app_pkg"], include_dependencies=False
    ) == [("app-repo", ["app_pkg"])]


def test_v4_unknown_dependency_fails(dependent_distribution):
    dependent_distribution["repositories"]["mid-repo"]["packages"]["mid_pkg"][
        "index_dependencies"
    ] = ["missing_pkg"]
    with pytest.raises(ComposeError, match="index dependency 'missing_pkg'.*not registered"):
        select_repositories(dependent_distribution, packages=["app_pkg"])


def test_v4_dependency_cycle_fails_with_path(dependent_distribution):
    dependent_distribution["repositories"]["leaf-repo"]["packages"]["leaf_pkg"][
        "index_dependencies"
    ] = ["app_pkg"]
    with pytest.raises(
        ComposeError, match="index dependency cycle: app_pkg -> mid_pkg -> leaf_pkg -> app_pkg"
    ):
        select_repositories(dependent_distribution, packages=["app_pkg"])


@pytest.mark.parametrize("dependencies", ["mid_pkg", None, ["mid_pkg", 7]])
def test_v4_invalid_dependency_list_fails(dependent_distribution, dependencies):
    dependent_distribution["repositories"]["app-repo"]["packages"]["app_pkg"][
        "index_dependencies"
    ] = dependencies
    with pytest.raises(ComposeError, match="invalid 'index_dependencies'"):
        select_repositories(dependent_distribution, packages=["app_pkg"])


def test_v4_dependency_output_is_deterministic(dependent_distribution):
    reversed_distribution = copy.deepcopy(dependent_distribution)
    reversed_distribution["repositories"] = dict(
        reversed(list(reversed_distribution["repositories"].items()))
    )
    app = reversed_distribution["repositories"]["app-repo"]["packages"]["app_pkg"]
    app["index_dependencies"].reverse()
    assert _selection_names(dependent_distribution, packages=["app_pkg"]) == _selection_names(
        reversed_distribution, packages=["app_pkg"]
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


def test_select_by_packages(sample_distribution):
    # A package filter keeps only the named packages, across whichever repos
    # host them; the monorepo entry lists only the matched package.
    selection = select_repositories(sample_distribution, packages=["alpha_sensing", "mid_pkg"])
    assert [(key, names) for key, _, names in selection] == [
        ("alpha-mono", ["alpha_sensing"]),
        ("mid-repo", ["mid_pkg"]),
    ]


def test_select_by_repository(sample_distribution):
    # A repository filter keeps whole entries by registry key, with all their
    # packages.
    selection = select_repositories(sample_distribution, repository=["alpha-mono"])
    assert [(key, names) for key, _, names in selection] == [
        ("alpha-mono", ["alpha_perception", "alpha_sensing"]),
    ]


def test_select_filters_are_anded(sample_distribution):
    # packages ∩ tags within the chosen repository.
    selection = select_repositories(
        sample_distribution,
        repository=["alpha-mono"],
        packages=["alpha_perception", "alpha_sensing"],
        tags=["sensing"],
    )
    assert [(key, names) for key, _, names in selection] == [
        ("alpha-mono", ["alpha_sensing"]),
    ]


def test_select_unknown_package_raises(sample_distribution):
    with pytest.raises(ComposeError, match="no such package in the distribution: 'nope'"):
        select_repositories(sample_distribution, packages=["nope"])


def test_select_unknown_repository_raises(sample_distribution):
    with pytest.raises(ComposeError, match="no such repository entry in the distribution: 'nope'"):
        select_repositories(sample_distribution, repository=["nope"])


def test_select_unknown_names_pluralized(sample_distribution):
    with pytest.raises(ComposeError, match="no such packages in the distribution:"):
        select_repositories(sample_distribution, packages=["nope", "alsonope"])


def test_select_existing_package_excluded_by_other_filter_is_not_unknown(
    sample_distribution,
):
    # alpha_sensing exists, but the repository filter excludes its repo: that is
    # an empty result, not an "unknown package" error.
    assert (
        select_repositories(
            sample_distribution, repository=["mid-repo"], packages=["alpha_sensing"]
        )
        == []
    )


def test_select_by_reference_design(sample_distribution):
    selected = select_repositories(sample_distribution, reference_design=True)
    assert [key for key, _spec, _names in selected] == ["alpha-mono"]


def test_select_reference_design_anded_with_tags(sample_distribution):
    selected = select_repositories(sample_distribution, tags=["perception"], reference_design=True)
    assert [(key, names) for key, _spec, names in selected] == [
        ("alpha-mono", ["alpha_perception"])
    ]


def test_unknown_tags_empty_without_filter(sample_distribution):
    assert unknown_tags(sample_distribution, None) == []
    assert unknown_tags(sample_distribution, []) == []


def test_unknown_tags_all_carried(sample_distribution):
    assert unknown_tags(sample_distribution, ["perception", "planning"]) == []


def test_unknown_tags_reports_absent_sorted(sample_distribution):
    assert unknown_tags(sample_distribution, ["zzz", "aaa", "perception"]) == ["aaa", "zzz"]


def test_unknown_tags_missing_repositories_key():
    assert unknown_tags({}, ["anything"]) == ["anything"]


def test_to_repos_entries_field_mapping(sample_distribution):
    repositories = select_repositories(sample_distribution)
    entries = to_repos_entries(repositories)
    # Order preserved (sorted by repository key).
    assert list(entries) == ["alpha-mono", "mid-repo", "zeta-stack"]
    # branch ref; pure vcs2l entry (no packages field, even for a monorepo)
    assert entries["alpha-mono"] == {
        "type": "git",
        "url": "https://github.com/example/alpha_mono",
        "version": "main",
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


def test_to_repos_entries_partial_selection_emits_pure_entry():
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
    # selected, and it is a pure vcs2l entry with no packages field.
    assert set(entries["mono"]) == {"type", "url", "version"}


def test_to_repos_entries_only_vcs2l_fields():
    """Regression guard: composed entries carry exactly type/url/version."""
    repositories = select_repositories(
        # build a minimal distribution inline to exercise every ref kind
        {
            "repositories": {
                "r": {
                    "url": "https://x/r",
                    "ref": {"kind": "branch", "value": "main"},
                    "packages": {"p": {"tags": ["t"]}},
                },
            }
        }
    )
    entries = to_repos_entries(repositories)
    assert all(set(e) == {"type", "url", "version"} for e in entries.values())


def test_to_repos_entries_missing_url_raises():
    with pytest.raises(ComposeError, match="url"):
        to_repos_entries([("r", {"ref": {"value": "main"}}, ["p"])])


def test_to_repos_entries_missing_ref_value_raises():
    with pytest.raises(ComposeError, match="ref.value"):
        to_repos_entries([("r", {"url": "https://x/r"}, ["p"])])


def test_to_repos_entries_none_spec_raises_url():
    with pytest.raises(ComposeError, match="url"):
        to_repos_entries([("r", None, ["p"])])


def test_to_repos_entries_ref_string_raises():
    with pytest.raises(
        ComposeError, match="repository 'r' has 'ref' that is not a mapping"
    ) as excinfo:
        to_repos_entries([("r", {"url": "https://x/r", "ref": "main"}, ["p"])])
    assert "got str" in str(excinfo.value)


def test_select_packages_list_raises():
    distribution = {
        "ros_distro": "jazzy",
        "repositories": {
            "r": {
                "url": "https://x/r",
                "ref": {"kind": "branch", "value": "main"},
                "packages": ["pkg_a", "pkg_b"],
            },
        },
    }
    with pytest.raises(
        ComposeError, match="repository 'r' has 'packages' that is not a mapping"
    ) as excinfo:
        select_repositories(distribution)
    assert "got list" in str(excinfo.value)
    # The same clean error under a tag filter (previously an AttributeError).
    with pytest.raises(ComposeError, match="'packages'"):
        select_repositories(distribution, tags=["sensing"])


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
    without = provenance_header(tool_version="0.1.0", ros_distro="jazzy", source="src")
    assert not any("autoware" in line for line in without)
    with_aw = provenance_header(
        tool_version="0.1.0", ros_distro="jazzy", source="src", autoware="2025.02"
    )
    aw_line = [line for line in with_aw if "autoware: 2025.02" in line]
    assert aw_line and "informational" in aw_line[0]


def test_provenance_header_generated_at_optional():
    without = provenance_header(tool_version="0.1.0", ros_distro="jazzy", source="src")
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


def test_provenance_header_records_packages_and_repository_filters():
    lines = provenance_header(
        tool_version="0.1.0",
        ros_distro="jazzy",
        source="src",
        packages=["alpha_sensing", "mid_pkg"],
        repository=["alpha-mono"],
    )
    assert "# packages: alpha_sensing, mid_pkg" in lines
    assert "# repository: alpha-mono" in lines


def test_provenance_header_records_reference_design_filter():
    lines = provenance_header(
        tool_version="0.1.0",
        ros_distro="jazzy",
        source="src",
        reference_design=True,
    )
    assert "# reference_design: true" in lines


def test_provenance_header_filter_lines_omitted_when_absent():
    lines = provenance_header(tool_version="0.1.0", ros_distro="jazzy", source="src")
    assert not any(line.startswith("# packages:") for line in lines)
    assert not any(line.startswith("# repository:") for line in lines)
    assert not any(line.startswith("# reference_design:") for line in lines)


def test_render_repos_valid_yaml_roundtrip(sample_distribution):
    header = provenance_header(tool_version="0.1.0", ros_distro="jazzy", source="src")
    text = render_repos(sample_distribution, header_lines=header)
    parsed = yaml.safe_load(text)
    assert parsed["repositories"]["alpha-mono"] == {
        "type": "git",
        "url": "https://github.com/example/alpha_mono",
        "version": "main",
    }
    assert list(parsed["repositories"]) == ["alpha-mono", "mid-repo", "zeta-stack"]


def test_render_repos_deterministic_without_generated_at(sample_distribution):
    header = provenance_header(tool_version="0.1.0", ros_distro="jazzy", source="src")
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
    # pure vcs2l entry: no packages field in the body
    assert "packages" not in parsed["repositories"]["mid-repo"]


def test_render_repos_monorepo_partial_selection(sample_distribution):
    header = provenance_header(
        tool_version="0.1.0", ros_distro="jazzy", source="src", tags=["sensing"]
    )
    text = render_repos(sample_distribution, tags=["sensing"], header_lines=header)
    parsed = yaml.safe_load(text)
    # The monorepo entry is still emitted for a partial selection, as a pure
    # vcs2l entry (no packages field).
    assert list(parsed["repositories"]) == ["alpha-mono"]
    assert "packages" not in parsed["repositories"]["alpha-mono"]


def test_render_repos_header_precedes_body_one_trailing_newline(sample_distribution):
    header = provenance_header(tool_version="0.1.0", ros_distro="jazzy", source="src")
    text = render_repos(sample_distribution, header_lines=header)
    lines = text.split("\n")
    # The rendered text starts with the first header line.
    assert text.startswith(header[0])
    # Every header line precedes the YAML body, in order.
    assert lines[: len(header)] == header
    # A single blank line separates the header from the body.
    assert lines[len(header)] == ""
    # The body starts on the line right after that blank separator.
    assert lines[len(header) + 1] == "repositories:"
    # Ends with exactly one trailing newline.
    assert text.endswith("\n")
    assert not text.endswith("\n\n")


def test_render_repos_empty_distribution():
    header = provenance_header(tool_version="0.1.0", ros_distro="jazzy", source="src")
    text = render_repos({"ros_distro": "jazzy", "repositories": {}}, header_lines=header)
    parsed = yaml.safe_load(text)
    assert parsed == {"repositories": {}}
