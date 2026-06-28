"""Tests for aw_index_cli.workspace."""

from __future__ import annotations

from pathlib import Path

from aw_index_cli.workspace import (
    discover_repos_files,
    find_repo_root,
    output_path,
)


def test_find_repo_root_in_start(tmp_path):
    (tmp_path / "repositories").mkdir()
    assert find_repo_root(tmp_path) == tmp_path.resolve()


def test_find_repo_root_ancestor(tmp_path):
    (tmp_path / "repositories").mkdir()
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    assert find_repo_root(deep) == tmp_path.resolve()


def test_find_repo_root_fallback(tmp_path):
    # No 'repositories' directory anywhere reachable in this isolated tree.
    deep = tmp_path / "x" / "y"
    deep.mkdir(parents=True)
    result = find_repo_root(deep)
    assert result == deep.resolve()


def test_output_path_shape(tmp_path):
    p = output_path(tmp_path)
    assert p == Path(tmp_path) / "repositories" / "autoware-index.repos"


def test_output_path_custom_name(tmp_path):
    p = output_path(tmp_path, name="my-stack")
    assert p.name == "my-stack.repos"
    assert p.parent.name == "repositories"


def test_discover_repos_files_in_cwd(tmp_path):
    direct = tmp_path / "autoware-index.repos"
    direct.write_text("repositories: {}\n")
    assert discover_repos_files(tmp_path) == [direct]


def test_discover_repos_files_one_level_deep(tmp_path):
    (tmp_path / "repositories").mkdir()
    nested = tmp_path / "repositories" / "autoware-index.repos"
    nested.write_text("repositories: {}\n")
    assert discover_repos_files(tmp_path) == [nested]


def test_discover_repos_files_direct_wins_over_deep(tmp_path):
    direct = tmp_path / "autoware-index.repos"
    direct.write_text("repositories: {}\n")
    (tmp_path / "repositories").mkdir()
    (tmp_path / "repositories" / "autoware-index.repos").write_text("repositories: {}\n")
    assert discover_repos_files(tmp_path) == [direct]


def test_discover_repos_files_multiple_deep(tmp_path):
    for sub in ("a", "b"):
        (tmp_path / sub).mkdir()
        (tmp_path / sub / "autoware-index.repos").write_text("repositories: {}\n")
    found = discover_repos_files(tmp_path)
    assert len(found) == 2
    assert found == sorted(found)


def test_discover_repos_files_none(tmp_path):
    assert discover_repos_files(tmp_path) == []
