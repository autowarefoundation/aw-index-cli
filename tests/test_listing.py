"""Tests for aw_index_cli.listing."""

from __future__ import annotations

from aw_index_cli.compose import select_repositories
from aw_index_cli.listing import evaluate
from aw_index_cli.registry import RegistryError


def _fetch(records):
    def fetch(package):
        value = records.get(package)
        if value == "__raise__":
            raise RegistryError("x")
        return value

    return fetch


def test_list_rows_have_status_and_meta(sample_distribution):
    selection = select_repositories(sample_distribution)
    records = {
        "alpha_sensing": {
            "status": "pass",
            "autoware_version": "1.8.0",
            "at": "2026-06-27T00:00:00Z",
        },
    }
    rows = evaluate(selection, fetch_record=_fetch(records))
    by_pkg = {r["package"]: r for r in rows}
    assert by_pkg["alpha_sensing"]["status"] == "pass"
    assert by_pkg["alpha_sensing"]["repo"] == "alpha-mono"
    assert by_pkg["alpha_sensing"]["ref"] == "branch main"
    assert "sensing" in by_pkg["alpha_sensing"]["tags"]
    assert by_pkg["alpha_sensing"]["validated"] == "2026-06-27"
    # no record → unknown, flagged as a problem (for --strict)
    assert by_pkg["mid_pkg"]["status"] == "—"
    assert by_pkg["mid_pkg"]["problem"]


def test_list_fail_is_problem(sample_distribution):
    selection = select_repositories(sample_distribution, repository=["mid-repo"])
    records = {"mid_pkg": {"status": "fail", "at": "2026-06-30T00:00:00Z"}}
    rows = evaluate(selection, fetch_record=_fetch(records))
    assert rows[0]["problem"]


def test_list_fetch_failure_is_unknown(sample_distribution):
    selection = select_repositories(sample_distribution, repository=["mid-repo"])
    rows = evaluate(selection, fetch_record=_fetch({"mid_pkg": "__raise__"}))
    assert rows[0]["status"] == "—"
    assert rows[0]["problem"]


def test_list_pass_is_not_problem(sample_distribution):
    selection = select_repositories(sample_distribution, repository=["mid-repo"])
    records = {"mid_pkg": {"status": "pass", "at": "2026-06-30T00:00:00Z"}}
    rows = evaluate(selection, fetch_record=_fetch(records))
    assert not rows[0]["problem"]
