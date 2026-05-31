"""Tests for aw_index_cli.cli."""

from __future__ import annotations

import yaml

from aw_index_cli.cli import main


def test_compose_writes_repos_file(distributions_dir, tmp_path, capsys):
    repo_root = tmp_path / "ws"
    (repo_root / "repositories").mkdir(parents=True)
    rc = main(
        [
            "compose",
            "--rosdistro",
            "jazzy",
            "--registry-path",
            str(distributions_dir),
            "--repo-root",
            str(repo_root),
        ]
    )
    assert rc == 0
    out_file = repo_root / "repositories" / "autoware-index.repos"
    assert out_file.is_file()
    parsed = yaml.safe_load(out_file.read_text())
    assert "alpha_pkg" in parsed["repositories"]
    err = capsys.readouterr().err
    assert "Wrote 3 package(s)" in err
    assert str(out_file) in err


def test_compose_creates_repositories_dir_when_missing(distributions_dir, tmp_path):
    repo_root = tmp_path / "fresh"
    repo_root.mkdir()
    rc = main(
        [
            "compose",
            "--rosdistro",
            "jazzy",
            "--registry-path",
            str(distributions_dir),
            "--repo-root",
            str(repo_root),
        ]
    )
    assert rc == 0
    assert (repo_root / "repositories" / "autoware-index.repos").is_file()


def test_compose_stdout_writes_no_file(distributions_dir, tmp_path, capsys):
    repo_root = tmp_path / "ws"
    (repo_root / "repositories").mkdir(parents=True)
    rc = main(
        [
            "compose",
            "--rosdistro",
            "jazzy",
            "--registry-path",
            str(distributions_dir),
            "--repo-root",
            str(repo_root),
            "--stdout",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    parsed = yaml.safe_load(out)
    assert "alpha_pkg" in parsed["repositories"]
    # Nothing written to disk.
    assert not (repo_root / "repositories" / "autoware-index.repos").exists()


def test_compose_tags_filter(distributions_dir, tmp_path, capsys):
    rc = main(
        [
            "compose",
            "--rosdistro",
            "jazzy",
            "--registry-path",
            str(distributions_dir),
            "--tags",
            "planning",
            "--stdout",
        ]
    )
    assert rc == 0
    parsed = yaml.safe_load(capsys.readouterr().out)
    assert list(parsed["repositories"]) == ["mid_pkg"]


def test_compose_explicit_output(distributions_dir, tmp_path):
    out = tmp_path / "custom" / "stack.repos"
    rc = main(
        [
            "compose",
            "--rosdistro",
            "jazzy",
            "--registry-path",
            str(distributions_dir),
            "--output",
            str(out),
        ]
    )
    assert rc == 0
    assert out.is_file()


def test_compose_missing_file_returns_1(tmp_path, capsys):
    rc = main(
        [
            "compose",
            "--rosdistro",
            "jazzy",
            "--registry-path",
            str(tmp_path),
        ]
    )
    assert rc == 1
    err = capsys.readouterr().err
    assert err.startswith("error:")


def test_stub_commands_return_2(capsys):
    for cmd in ("import", "sync", "check", "refresh"):
        rc = main([cmd])
        assert rc == 2
        err = capsys.readouterr().err
        assert f"aw-index-cli {cmd} is not implemented yet" in err


def test_no_subcommand_returns_2(capsys):
    rc = main([])
    assert rc == 2
    out = capsys.readouterr().out
    assert "usage" in out.lower()


def test_compose_output_wins_over_repo_root(distributions_dir, tmp_path):
    repo_root = tmp_path / "ws"
    (repo_root / "repositories").mkdir(parents=True)
    out = tmp_path / "custom" / "stack.repos"
    rc = main(
        [
            "compose",
            "--rosdistro",
            "jazzy",
            "--registry-path",
            str(distributions_dir),
            "--repo-root",
            str(repo_root),
            "--output",
            str(out),
        ]
    )
    assert rc == 0
    assert out.is_file()
    # The discoverable repositories/ dir was not written to.
    assert not (repo_root / "repositories" / "autoware-index.repos").exists()


def test_compose_writes_under_cwd_repositories(distributions_dir, tmp_path, monkeypatch):
    workdir = tmp_path / "work"
    (workdir / "repositories").mkdir(parents=True)
    monkeypatch.chdir(workdir)
    rc = main(
        [
            "compose",
            "--rosdistro",
            "jazzy",
            "--registry-path",
            str(distributions_dir),
        ]
    )
    assert rc == 0
    assert (workdir / "repositories" / "autoware-index.repos").is_file()


def test_compose_stdout_no_file_no_wrote_line(distributions_dir, tmp_path, capsys):
    repo_root = tmp_path / "ws"
    (repo_root / "repositories").mkdir(parents=True)
    rc = main(
        [
            "compose",
            "--rosdistro",
            "jazzy",
            "--registry-path",
            str(distributions_dir),
            "--repo-root",
            str(repo_root),
            "--stdout",
        ]
    )
    assert rc == 0
    captured = capsys.readouterr()
    assert "Wrote" not in captured.err
    assert captured.out.startswith("# aw-index-cli")
    parsed = yaml.safe_load(captured.out)
    assert "alpha_pkg" in parsed["repositories"]
    assert not (repo_root / "repositories" / "autoware-index.repos").exists()


def test_compose_stdout_header_lines_present(distributions_dir, capsys):
    rc = main(
        [
            "compose",
            "--rosdistro",
            "jazzy",
            "--registry-path",
            str(distributions_dir),
            "--tags",
            "sensing",
            "--autoware",
            "2025.02",
            "--stdout",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "# rosdistro: jazzy" in out
    assert "# tags: sensing" in out
    assert "# autoware: 2025.02" in out


def test_compose_no_timestamp_byte_identical(distributions_dir, capsys):
    args = [
        "compose",
        "--rosdistro",
        "jazzy",
        "--registry-path",
        str(distributions_dir),
        "--stdout",
        "--no-timestamp",
    ]
    assert main(args) == 0
    first = capsys.readouterr().out
    assert main(args) == 0
    second = capsys.readouterr().out
    assert first == second
    assert "# generated_at:" not in first


def test_compose_default_includes_generated_at(distributions_dir, capsys):
    rc = main(
        [
            "compose",
            "--rosdistro",
            "jazzy",
            "--registry-path",
            str(distributions_dir),
            "--stdout",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "# generated_at:" in out
