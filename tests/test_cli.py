"""Tests for aw_index_cli.cli."""

from __future__ import annotations

import json

import yaml

from aw_index_cli import cli, registry
from aw_index_cli.cli import main

_PASS = (
    '{{"status":"pass","autoware_version":"1.8.0",'
    '"at":"2026-06-27T00:00:00Z","resolved_sha":"{sha}"}}\n'
)


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
    assert "alpha-mono" in parsed["repositories"]
    err = capsys.readouterr().err
    assert "Wrote 3 repository entries covering 4 registered package(s)" in err
    assert "alpha-mono (alpha_perception, alpha_sensing)" in err
    assert "mid-repo (mid_pkg)" in err
    assert "zeta-stack (zeta_pkg)" in err
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
    assert "alpha-mono" in parsed["repositories"]
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
    assert list(parsed["repositories"]) == ["mid-repo"]
    assert "packages" not in parsed["repositories"]["mid-repo"]


def test_compose_monorepo_partial_selection(distributions_dir, capsys):
    # Only one of the monorepo's two packages carries the tag: the entry is
    # still emitted, and its manifest lists only the selected package.
    rc = main(
        [
            "compose",
            "--rosdistro",
            "jazzy",
            "--registry-path",
            str(distributions_dir),
            "--tags",
            "sensing",
            "--stdout",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    parsed = yaml.safe_load(out)
    assert list(parsed["repositories"]) == ["alpha-mono"]
    # pure vcstool entry; the selected package is named only in the header comment
    assert "packages" not in parsed["repositories"]["alpha-mono"]
    assert "#   alpha-mono: alpha_sensing" in out


def test_compose_packages_selection(distributions_dir, capsys):
    rc = main(
        [
            "compose",
            "--rosdistro",
            "jazzy",
            "--registry-path",
            str(distributions_dir),
            "--packages",
            "alpha_sensing",
            "mid_pkg",
            "--stdout",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    parsed = yaml.safe_load(out)
    assert list(parsed["repositories"]) == ["alpha-mono", "mid-repo"]
    assert "# packages: alpha_sensing, mid_pkg" in out
    assert "#   alpha-mono: alpha_sensing" in out


def test_compose_repository_selection(distributions_dir, capsys):
    rc = main(
        [
            "compose",
            "--rosdistro",
            "jazzy",
            "--registry-path",
            str(distributions_dir),
            "--repository",
            "mid-repo",
            "--stdout",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    parsed = yaml.safe_load(out)
    assert list(parsed["repositories"]) == ["mid-repo"]
    assert "# repository: mid-repo" in out


def test_compose_unknown_package_clean_error(distributions_dir, capsys):
    rc = main(
        [
            "compose",
            "--rosdistro",
            "jazzy",
            "--registry-path",
            str(distributions_dir),
            "--packages",
            "nope",
            "--stdout",
        ]
    )
    assert rc == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "no such package in the distribution: 'nope'" in captured.err


def test_compose_unknown_repository_clean_error(distributions_dir, capsys):
    rc = main(
        [
            "compose",
            "--rosdistro",
            "jazzy",
            "--registry-path",
            str(distributions_dir),
            "--repository",
            "nope",
            "--stdout",
        ]
    )
    assert rc == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "no such repository entry in the distribution: 'nope'" in captured.err


def test_compose_single_repo_summary_is_singular(distributions_dir, tmp_path, capsys):
    out_file = tmp_path / "one.repos"
    rc = main(
        [
            "compose",
            "--rosdistro",
            "jazzy",
            "--registry-path",
            str(distributions_dir),
            "--tags",
            "planning",
            "--output",
            str(out_file),
        ]
    )
    assert rc == 0
    err = capsys.readouterr().err
    assert "Wrote 1 repository entry covering 1 registered package(s)" in err
    assert "mid-repo (mid_pkg)" in err


def test_compose_rejects_schema_version_1(tmp_path, capsys):
    dist_dir = tmp_path / "distributions"
    dist_dir.mkdir()
    (dist_dir / "jazzy.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": "1",
                "ros_distro": "jazzy",
                "packages": {
                    "old_pkg": {
                        "repository": "https://x/old_pkg",
                        "tags": ["sensing"],
                        "ref": {"kind": "branch", "value": "main"},
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    rc = main(
        [
            "compose",
            "--rosdistro",
            "jazzy",
            "--registry-path",
            str(tmp_path),
            "--stdout",
        ]
    )
    assert rc == 1
    captured = capsys.readouterr()
    # No silent empty output: nothing on stdout, a clear error on stderr.
    assert captured.out == ""
    assert captured.err.startswith("error:")
    assert "'1'" in captured.err
    assert "not supported by this aw-index-cli" in captured.err
    assert "(supports: '2')" in captured.err
    # The document is older than the CLI, so no "please upgrade" advice.
    assert "upgrade" not in captured.err


def _compose_malformed(tmp_path, capsys, doc):
    """Run compose against ``doc`` and assert a clean error, returning stderr."""
    dist_dir = tmp_path / "distributions"
    dist_dir.mkdir()
    (dist_dir / "jazzy.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    rc = main(
        [
            "compose",
            "--rosdistro",
            "jazzy",
            "--registry-path",
            str(tmp_path),
            "--stdout",
        ]
    )
    assert rc == 1
    captured = capsys.readouterr()
    # Clean failure: nothing on stdout, a single error line, no traceback.
    assert captured.out == ""
    assert captured.err.startswith("error:")
    assert "Traceback" not in captured.err
    return captured.err


def test_compose_repositories_list_clean_error(tmp_path, capsys):
    err = _compose_malformed(
        tmp_path,
        capsys,
        {
            "schema_version": "2",
            "ros_distro": "jazzy",
            "repositories": ["alpha-mono"],
        },
    )
    assert "'repositories' must be a mapping" in err


def test_compose_repository_entry_string_clean_error(tmp_path, capsys):
    err = _compose_malformed(
        tmp_path,
        capsys,
        {
            "schema_version": "2",
            "ros_distro": "jazzy",
            "repositories": {"alpha-mono": "https://x/alpha_mono"},
        },
    )
    assert "repository 'alpha-mono' must be a mapping" in err


def test_compose_ref_string_clean_error(tmp_path, capsys):
    err = _compose_malformed(
        tmp_path,
        capsys,
        {
            "schema_version": "2",
            "ros_distro": "jazzy",
            "repositories": {
                "alpha-mono": {
                    "url": "https://x/alpha_mono",
                    "ref": "main",
                    "packages": {"alpha_pkg": {"tags": ["sensing"]}},
                },
            },
        },
    )
    assert "repository 'alpha-mono' has 'ref' that is not a mapping" in err


def test_compose_packages_list_clean_error(tmp_path, capsys):
    err = _compose_malformed(
        tmp_path,
        capsys,
        {
            "schema_version": "2",
            "ros_distro": "jazzy",
            "repositories": {
                "alpha-mono": {
                    "url": "https://x/alpha_mono",
                    "ref": {"kind": "branch", "value": "main"},
                    "packages": ["alpha_pkg"],
                },
            },
        },
    )
    assert "repository 'alpha-mono' has 'packages' that is not a mapping" in err


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
    assert "alpha-mono" in parsed["repositories"]
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
    assert "# selected packages by repository:" in out


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


# --- list ----------------------------------------------------------------------
def test_list_command_table(distributions_dir, monkeypatch, capsys, history_urlopen):
    records = {"alpha_sensing": _PASS.format(sha="s")}
    monkeypatch.setattr(registry, "urlopen", history_urlopen(records))
    rc = main(["list", "--rosdistro", "jazzy", "--registry-path", str(distributions_dir)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "PACKAGE" in out
    assert "alpha_sensing" in out and "pass" in out


def test_list_strict_exits_1_on_unvalidated(
    distributions_dir, monkeypatch, capsys, history_urlopen
):
    monkeypatch.setattr(registry, "urlopen", history_urlopen({}))  # everything 404
    rc = main(
        [
            "list",
            "--rosdistro",
            "jazzy",
            "--registry-path",
            str(distributions_dir),
            "--strict",
        ]
    )
    assert rc == 1


def test_list_json(distributions_dir, monkeypatch, capsys, history_urlopen):
    monkeypatch.setattr(registry, "urlopen", history_urlopen({}))
    rc = main(
        [
            "list",
            "--rosdistro",
            "jazzy",
            "--registry-path",
            str(distributions_dir),
            "--repository",
            "mid-repo",
            "--format",
            "json",
        ]
    )
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["rosdistro"] == "jazzy"
    assert data["rows"][0]["package"] == "mid_pkg"


# --- check ---------------------------------------------------------------------
def _all_pass_records(sha="s"):
    return {
        p: _PASS.format(sha=sha)
        for p in ("alpha_sensing", "alpha_perception", "mid_pkg", "zeta_pkg")
    }


def test_check_with_repos_file_passes(
    tmp_path, distributions_dir, sample_repos_text, monkeypatch, capsys, history_urlopen
):
    repos_file = tmp_path / "autoware-index.repos"
    repos_file.write_text(sample_repos_text)
    monkeypatch.setattr(registry, "urlopen", history_urlopen(_all_pass_records()))
    monkeypatch.setattr(cli, "remote_sha", lambda url, ref: "s")  # no branch drift
    rc = main(
        [
            "check",
            "--repos",
            str(repos_file),
            "--registry-path",
            str(distributions_dir),
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "alpha_sensing" in out and "pass" in out


def test_check_autodiscovers_one_level_deep(
    tmp_path, distributions_dir, sample_repos_text, monkeypatch, capsys, history_urlopen
):
    (tmp_path / "repositories").mkdir()
    (tmp_path / "repositories" / "autoware-index.repos").write_text(sample_repos_text)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(registry, "urlopen", history_urlopen({}))  # unvalidated (soft)
    monkeypatch.setattr(cli, "remote_sha", lambda url, ref: None)
    rc = main(["check", "--registry-path", str(distributions_dir)])
    assert rc == 0  # unvalidated is not a problem without --strict


def test_check_ref_drift_exits_1(
    tmp_path, distributions_dir, sample_repos_text, monkeypatch, capsys, history_urlopen
):
    drifted = sample_repos_text.replace("version: v1.2.3", "version: v1.0.0")
    repos_file = tmp_path / "autoware-index.repos"
    repos_file.write_text(drifted)
    monkeypatch.setattr(registry, "urlopen", history_urlopen(_all_pass_records()))
    monkeypatch.setattr(cli, "remote_sha", lambda url, ref: "s")
    rc = main(
        ["check", "--repos", str(repos_file), "--registry-path", str(distributions_dir)]
    )
    assert rc == 1
    assert "registry moved" in capsys.readouterr().out


def test_check_rosdistro_from_header(
    tmp_path, distributions_dir, sample_repos_text, monkeypatch, capsys, history_urlopen
):
    repos_file = tmp_path / "autoware-index.repos"
    repos_file.write_text(sample_repos_text)
    monkeypatch.setattr(registry, "urlopen", history_urlopen(_all_pass_records()))
    monkeypatch.setattr(cli, "remote_sha", lambda url, ref: "s")
    # no --rosdistro: must be read from the .repos header
    rc = main(
        ["check", "--repos", str(repos_file), "--registry-path", str(distributions_dir)]
    )
    assert rc == 0


def test_check_missing_repos_file_exits_2(tmp_path, distributions_dir, capsys):
    rc = main(
        [
            "check",
            "--repos",
            str(tmp_path / "nope.repos"),
            "--registry-path",
            str(distributions_dir),
        ]
    )
    assert rc == 2
    assert "error:" in capsys.readouterr().err


def test_check_no_autodiscovery_exits_2(tmp_path, monkeypatch, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.chdir(empty)
    rc = main(["check"])
    assert rc == 2
    assert "no autoware-index.repos" in capsys.readouterr().err


def test_check_json(
    tmp_path, distributions_dir, sample_repos_text, monkeypatch, capsys, history_urlopen
):
    repos_file = tmp_path / "autoware-index.repos"
    repos_file.write_text(sample_repos_text)
    monkeypatch.setattr(registry, "urlopen", history_urlopen(_all_pass_records()))
    monkeypatch.setattr(cli, "remote_sha", lambda url, ref: "s")
    rc = main(
        [
            "check",
            "--repos",
            str(repos_file),
            "--registry-path",
            str(distributions_dir),
            "--format",
            "json",
        ]
    )
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["rosdistro"] == "jazzy"
    assert data["problems"] == 0
    assert {r["package"] for r in data["rows"]} >= {"alpha_sensing", "mid_pkg"}


def test_check_unvalidated_soft_without_strict_hard_with_strict(
    tmp_path, distributions_dir, sample_repos_text, monkeypatch, capsys, history_urlopen
):
    repos_file = tmp_path / "autoware-index.repos"
    repos_file.write_text(sample_repos_text)
    monkeypatch.setattr(registry, "urlopen", history_urlopen({}))  # all 404 -> unvalidated
    monkeypatch.setattr(cli, "remote_sha", lambda url, ref: None)
    base = ["check", "--repos", str(repos_file), "--registry-path", str(distributions_dir)]
    # unvalidated is a soft problem: clean (exit 0) without --strict ...
    assert main(base) == 0
    capsys.readouterr()
    # ... and a failure (exit 1) with --strict.
    assert main(base + ["--strict"]) == 1


def test_check_branch_drift_warns_without_strict(
    tmp_path, distributions_dir, sample_repos_text, monkeypatch, capsys, history_urlopen
):
    repos_file = tmp_path / "autoware-index.repos"
    repos_file.write_text(sample_repos_text)
    # records were swept at "OLD"; the live branch HEAD is "NEW" -> advanced
    monkeypatch.setattr(registry, "urlopen", history_urlopen(_all_pass_records(sha="OLD")))
    monkeypatch.setattr(cli, "remote_sha", lambda url, ref: "NEW")
    rc = main(
        ["check", "--repos", str(repos_file), "--registry-path", str(distributions_dir)]
    )
    out = capsys.readouterr().out
    assert rc == 0  # branch advance is a warning, not a default failure
    assert "branch advanced" in out


def test_check_branch_drift_fails_with_strict(
    tmp_path, distributions_dir, sample_repos_text, monkeypatch, capsys, history_urlopen
):
    repos_file = tmp_path / "autoware-index.repos"
    repos_file.write_text(sample_repos_text)
    monkeypatch.setattr(registry, "urlopen", history_urlopen(_all_pass_records(sha="OLD")))
    monkeypatch.setattr(cli, "remote_sha", lambda url, ref: "NEW")
    rc = main(
        [
            "check",
            "--repos",
            str(repos_file),
            "--registry-path",
            str(distributions_dir),
            "--strict",
        ]
    )
    assert rc == 1


def test_check_multiple_autodiscovered_exits_2(tmp_path, sample_repos_text, monkeypatch, capsys):
    for sub in ("a", "b"):
        (tmp_path / sub).mkdir()
        (tmp_path / sub / "autoware-index.repos").write_text(sample_repos_text)
    monkeypatch.chdir(tmp_path)
    rc = main(["check"])
    assert rc == 2
    assert "multiple autoware-index.repos" in capsys.readouterr().err


def test_check_missing_rosdistro_exits_2(tmp_path, distributions_dir, capsys):
    repos_file = tmp_path / "autoware-index.repos"
    repos_file.write_text(
        "repositories:\n  r:\n    type: git\n    url: https://x/r\n    version: main\n"
    )
    rc = main(
        ["check", "--repos", str(repos_file), "--registry-path", str(distributions_dir)]
    )
    assert rc == 2
    assert "could not determine the rosdistro" in capsys.readouterr().err


def test_check_read_error_exits_2(tmp_path, distributions_dir, monkeypatch, capsys):
    import pathlib

    repos_file = tmp_path / "autoware-index.repos"
    repos_file.write_text("repositories: {}\n")
    real_read_text = pathlib.Path.read_text

    def boom(self, *args, **kwargs):
        if self == repos_file:
            raise OSError("permission denied")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "read_text", boom)
    rc = main(
        ["check", "--repos", str(repos_file), "--registry-path", str(distributions_dir)]
    )
    assert rc == 2
    assert "could not read" in capsys.readouterr().err
