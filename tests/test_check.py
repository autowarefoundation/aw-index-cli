"""Tests for aw_index_cli.check."""

from __future__ import annotations

import pytest

from aw_index_cli.check import (
    CheckError,
    evaluate,
    parse_repos,
    rosdistro_from_header,
    selected_packages_from_header,
)
from aw_index_cli.registry import RegistryError

ALPHA_URL = "https://github.com/example/alpha_mono"
MID_URL = "https://github.com/example/mid_repo"
ZETA_URL = "https://github.com/example/zeta_stack"


# --- parse_repos ---------------------------------------------------------------
def test_parse_repos_ok():
    text = (
        "repositories:\n"
        "  r:\n"
        "    type: git\n"
        "    url: https://x/r\n"
        "    version: main\n"
    )
    assert parse_repos(text) == {"r": {"url": "https://x/r", "version": "main"}}


def test_parse_repos_no_repositories_raises():
    with pytest.raises(CheckError):
        parse_repos("foo: bar\n")


def test_parse_repos_bad_yaml_raises():
    with pytest.raises(CheckError):
        parse_repos("repositories: [unclosed\n")


# --- header parsing ------------------------------------------------------------
def test_rosdistro_from_header():
    assert rosdistro_from_header("# rosdistro: jazzy\n") == "jazzy"


def test_rosdistro_from_header_absent():
    assert rosdistro_from_header("# something else\n") is None


def test_selected_packages_from_header():
    text = (
        "# selected packages by repository:\n"
        "#   alpha-mono: alpha_perception, alpha_sensing\n"
        "#   mid-repo: mid_pkg\n"
        "# Generated file\n"
        "repositories: {}\n"
    )
    assert selected_packages_from_header(text) == {
        "alpha-mono": ["alpha_perception", "alpha_sensing"],
        "mid-repo": ["mid_pkg"],
    }


def test_selected_packages_from_header_absent():
    assert selected_packages_from_header("# rosdistro: jazzy\n") == {}


# --- evaluate ------------------------------------------------------------------
def _fetch(records):
    def fetch(package):
        value = records.get(package, "__none__")
        if value == "__raise__":
            raise RegistryError("boom")
        if value == "__none__":
            return None
        return value

    return fetch


def _no_sha(url, ref):
    return None


def test_evaluate_all_pass(sample_distribution):
    repos = {
        "alpha-mono": {"url": ALPHA_URL, "version": "main"},
        "mid-repo": {"url": MID_URL, "version": "v1.2.3"},
        "zeta-stack": {"url": ZETA_URL, "version": "a" * 40},
    }
    record = {
        "status": "pass",
        "autoware_version": "1.8.0",
        "at": "2026-06-27T00:00:00Z",
        "resolved_sha": "s",
    }
    records = {
        p: record
        for p in ("alpha_sensing", "alpha_perception", "mid_pkg", "zeta_pkg")
    }
    rows = evaluate(
        repos, sample_distribution, {}, fetch_record=_fetch(records), resolve_sha=_no_sha
    )
    assert {r["package"] for r in rows} == set(records)
    assert all(not r["problem"] for r in rows)


def test_evaluate_fail_is_problem(sample_distribution):
    repos = {"mid-repo": {"url": MID_URL, "version": "v1.2.3"}}
    records = {"mid_pkg": {"status": "fail", "autoware_version": "1.9.0", "at": "x"}}
    rows = evaluate(
        repos, sample_distribution, {}, fetch_record=_fetch(records), resolve_sha=_no_sha
    )
    assert rows[0]["problem"]
    assert rows[0]["status"] == "fail"


def test_evaluate_ref_drift_is_problem(sample_distribution):
    repos = {"mid-repo": {"url": MID_URL, "version": "v1.0.0"}}
    records = {"mid_pkg": {"status": "pass", "at": "2026-06-01T00:00:00Z"}}
    rows = evaluate(
        repos, sample_distribution, {}, fetch_record=_fetch(records), resolve_sha=_no_sha
    )
    assert rows[0]["problem"]
    assert "registry moved" in rows[0]["note"]
    assert "v1.0.0 → v1.2.3" in rows[0]["ref"]


def test_evaluate_removed_repo_is_problem(sample_distribution):
    repos = {"ghost": {"url": "https://x/ghost", "version": "main"}}
    rows = evaluate(
        repos, sample_distribution, {}, fetch_record=_fetch({}), resolve_sha=_no_sha
    )
    assert rows[0]["problem"]
    assert rows[0]["package"] == "ghost"
    assert "removed" in rows[0]["note"]


def test_evaluate_unvalidated_soft_unless_strict(sample_distribution):
    repos = {"mid-repo": {"url": MID_URL, "version": "v1.2.3"}}
    rows = evaluate(
        repos, sample_distribution, {}, fetch_record=_fetch({}), resolve_sha=_no_sha
    )
    assert not rows[0]["problem"]
    assert "unvalidated" in rows[0]["note"]
    strict_rows = evaluate(
        repos,
        sample_distribution,
        {},
        fetch_record=_fetch({}),
        resolve_sha=_no_sha,
        strict=True,
    )
    assert strict_rows[0]["problem"]


def test_evaluate_fetch_failure_is_soft(sample_distribution):
    repos = {"mid-repo": {"url": MID_URL, "version": "v1.2.3"}}
    rows = evaluate(
        repos,
        sample_distribution,
        {},
        fetch_record=_fetch({"mid_pkg": "__raise__"}),
        resolve_sha=_no_sha,
    )
    assert not rows[0]["problem"]
    assert "fetch failed" in rows[0]["note"]


def test_evaluate_branch_head_drift_warns(sample_distribution):
    repos = {"alpha-mono": {"url": ALPHA_URL, "version": "main"}}
    records = {
        p: {"status": "pass", "at": "2026-06-01T00:00:00Z", "resolved_sha": "OLD"}
        for p in ("alpha_sensing", "alpha_perception")
    }
    rows = evaluate(
        repos,
        sample_distribution,
        {},
        fetch_record=_fetch(records),
        resolve_sha=lambda url, ref: "NEW",
    )
    assert all("branch advanced since sweep" in r["note"] for r in rows)
    assert all(not r["problem"] for r in rows)  # warning only
    strict_rows = evaluate(
        repos,
        sample_distribution,
        {},
        fetch_record=_fetch(records),
        resolve_sha=lambda url, ref: "NEW",
        strict=True,
    )
    assert all(r["problem"] for r in strict_rows)


def test_evaluate_package_scope_uses_header_selection(sample_distribution):
    repos = {"alpha-mono": {"url": ALPHA_URL, "version": "main"}}
    records = {"alpha_sensing": {"status": "pass", "at": "2026-06-01T00:00:00Z"}}
    rows = evaluate(
        repos,
        sample_distribution,
        {"alpha-mono": ["alpha_sensing"]},
        fetch_record=_fetch(records),
        resolve_sha=_no_sha,
    )
    # only the header-selected package, not its sibling alpha_perception
    assert [r["package"] for r in rows] == ["alpha_sensing"]
