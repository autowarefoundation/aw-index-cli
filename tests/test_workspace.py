"""Tests for aw_index_cli.workspace."""

from __future__ import annotations

from pathlib import Path

from aw_index_cli.workspace import find_repo_root, output_path


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
