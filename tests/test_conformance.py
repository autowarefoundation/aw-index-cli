"""Conformance: ``js/compose.mjs`` must match the Python compose in content.

The browse site reuses ``js/compose.mjs`` to build ``.repos`` files; this test is
the guarantee that the JS port cannot silently diverge from the reference Python
implementation. It runs both over identical inputs and asserts identical content
— same parsed YAML body and same ``#`` header lines — while allowing byte-level
formatting (scalar quoting, line wrapping) to differ, since it reparses the same.

Requires ``node`` on PATH (skipped otherwise); kept out of the pure-offline unit
suite's guarantees but runs in CI's dedicated conformance job.
"""

from __future__ import annotations

import json
from pathlib import Path
import random
import re
import shutil
import subprocess

import pytest
import yaml

from aw_index_cli import __version__
from aw_index_cli.compose import provenance_header
from aw_index_cli.compose import render_repos
from aw_index_cli.compose import select_repositories

REPO_ROOT = Path(__file__).resolve().parent.parent
JS_DIR = REPO_ROOT / "js"
DRIVER = JS_DIR / "conformance_driver.mjs"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

# Common provenance the site would pass (matches the default network CLI run).
BASE = {
    "rosDistro": "jazzy",
    "source": "autowarefoundation/autoware-index@main",
    "toolVersion": __version__,
}

# A distribution that exercises yamlScalar edge cases: a bool-like repo key
# ("on") and a numeric-looking ref value ("1.20"), both of which PyYAML quotes.
ADVERSARIAL = {
    "schema_version": "2",
    "ros_distro": "jazzy",
    "repositories": {
        "on": {
            "url": "https://github.com/example/on_repo",
            "ref": {"kind": "tag", "value": "1.20"},
            "packages": {"on_pkg": {"tags": ["x"]}},
        },
        "normal": {
            "url": "https://github.com/example/normal",
            "ref": {"kind": "branch", "value": "main"},
            "packages": {"normal_pkg": {"tags": ["y"]}},
        },
    },
}

# Empty/absent package containers must be handled identically on both sides
# (Python's ``... or {}`` vs JS's truthy ``[]``): such a repo selects nothing
# and drops out, rather than erroring on one side only.
EMPTY_CONTAINERS = {
    "schema_version": "2",
    "ros_distro": "jazzy",
    "repositories": {
        "empty_list": {
            "url": "https://github.com/example/empty_list",
            "ref": {"kind": "branch", "value": "main"},
            "packages": [],
        },
        "empty_map": {
            "url": "https://github.com/example/empty_map",
            "ref": {"kind": "branch", "value": "main"},
            "packages": {},
        },
        "kept": {
            "url": "https://github.com/example/kept",
            "ref": {"kind": "tag", "value": "v1.0.0"},
            "packages": {"kept_pkg": {"tags": ["z"]}},
        },
    },
}


def _py_compose(distribution: dict, opts: dict) -> str:
    tags = opts.get("tags")
    packages = opts.get("packages")
    repository = opts.get("repository")
    selection = [
        (key, names)
        for key, _spec, names in select_repositories(
            distribution, tags=tags, packages=packages, repository=repository
        )
    ]
    header = provenance_header(
        tool_version=opts["toolVersion"],
        ros_distro=opts["rosDistro"],
        source=opts["source"],
        tags=tags,
        packages=packages,
        repository=repository,
        autoware=opts.get("autoware"),
        generated_at=opts.get("generatedAt"),
        selection=selection,
    )
    return render_repos(
        distribution, tags=tags, packages=packages, repository=repository, header_lines=header
    )


def _js_compose(distribution: dict, opts: dict) -> str:
    payload = json.dumps({"distribution": distribution, "options": opts})
    proc = subprocess.run(
        [NODE, str(DRIVER)],
        input=payload,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def _assert_same_content(js: str, py: str) -> None:
    """Assert the two ``.repos`` documents carry identical content.

    Content is the parsed YAML body plus the ``#`` provenance header lines
    (comments are invisible to the parser, so they are compared separately).
    Byte-level formatting — scalar quoting, line folding, the explicit ``? key``
    form for long keys — may differ; it reparses to the same content.
    """
    assert yaml.safe_load(js) == yaml.safe_load(py)
    js_header = [line for line in js.splitlines() if line.startswith("#")]
    py_header = [line for line in py.splitlines() if line.startswith("#")]
    assert js_header == py_header


@pytest.mark.parametrize(
    "opts",
    [
        {},
        {"tags": ["perception"]},
        {"packages": ["alpha_sensing"]},
        {"packages": ["mid_pkg", "zeta_pkg"]},
        {"packages": ["zeta_pkg", "alpha_sensing"]},
        {"repository": ["alpha-mono"]},
        {"autoware": "2025.02"},
        {"generatedAt": "2026-01-01T00:00:00+00:00"},  # the default CLI header line
        {"tags": ["nonexistent"]},  # empty selection -> `repositories: {}`
    ],
)
def test_js_matches_python(sample_distribution, opts):
    merged = {**BASE, **opts}
    _assert_same_content(
        _js_compose(sample_distribution, merged), _py_compose(sample_distribution, merged)
    )


@pytest.mark.parametrize("opts", [{}, {"packages": ["kept_pkg"]}])
def test_js_matches_python_empty_containers(opts):
    merged = {**BASE, **opts}
    _assert_same_content(
        _js_compose(EMPTY_CONTAINERS, merged), _py_compose(EMPTY_CONTAINERS, merged)
    )


@pytest.mark.parametrize("opts", [{}, {"packages": ["on_pkg"]}])
def test_js_matches_python_adversarial_scalars(opts):
    merged = {**BASE, **opts}
    _assert_same_content(_js_compose(ADVERSARIAL, merged), _py_compose(ADVERSARIAL, merged))


def test_js_version_matches_python():
    text = (JS_DIR / "compose.mjs").read_text(encoding="utf-8")
    match = re.search(r'export const VERSION = "([^"]+)";', text)
    assert match, "VERSION constant not found in compose.mjs"
    assert match.group(1) == __version__


def _single_repo_dist(*, key: str, ref_value: str) -> dict:
    """Return a minimal one-repo distribution with the given key and ref value."""
    return {
        "schema_version": "2",
        "ros_distro": "jazzy",
        "repositories": {
            key: {
                "url": "https://github.com/example/repo",
                "ref": {"kind": "tag", "value": ref_value},
                "packages": {"pkg": {"tags": ["t"]}},
            },
        },
    }


# Registry-realistic scalars that sit on PyYAML's implicit-resolver boundaries
# (bool/int/float/null/timestamp/sexagesimal). The committed fixtures only
# exercised "1.20"/"on"; this drives the whole resolver-sensitive set end-to-end.
# This is the load-bearing content check: if a RESOLVERS regex in compose.mjs
# ever drifts from the installed PyYAML, one side leaves a scalar plain and it
# reloads as the wrong type — a *content* difference the assertion catches here
# rather than in production.
RESOLVER_BOUNDARY_SCALARS = [
    "no",
    "off",
    "yes",
    "on",
    "true",
    "false",
    "null",
    "~",
    "1.20",
    "1.0",
    "1e3",
    "1.5e3",
    "089",
    "0755",
    "0x10",
    "0b10",
    "123",
    "-5",
    "+5",
    "1_000",
    "2026-01-01",
    "12:30",
    "1:2:3",
    ".inf",
    ".nan",
    "main",
    "v1.2.3",
    "release/2025.02",
]


@pytest.mark.parametrize("scalar", RESOLVER_BOUNDARY_SCALARS)
def test_js_matches_python_resolver_boundary(scalar):
    dist = _single_repo_dist(key="example/repo", ref_value=scalar)
    _assert_same_content(_js_compose(dist, BASE), _py_compose(dist, BASE))


@pytest.mark.parametrize(
    "key, ref_value",
    [
        ("example/repo", "v" + "1" * 200),  # long, space-free: neither side folds
        ("example/repo", ("relX " * 40).strip()),  # long, spaced: PyYAML folds, JS does not
        ("example/repo", "release " * 30),  # trailing space: PyYAML quotes + folds
        ("org/" + "r" * 130, "main"),  # >=123-char key: PyYAML uses `? key`, JS inline
        ("example/repo", "café-naïve"),  # non-ASCII: PyYAML escapes, JS emits plain
    ],
)
def test_js_matches_python_formatting_may_differ(key, ref_value):
    # Inputs where PyYAML and the JS port emit *different bytes* (line folding,
    # quoting, the explicit `? key` form, non-ASCII escaping) yet parse to the
    # same content — exactly what the content contract allows and the old
    # byte-for-byte contract forbade.
    dist = _single_repo_dist(key=key, ref_value=ref_value)
    _assert_same_content(_js_compose(dist, BASE), _py_compose(dist, BASE))


def test_js_matches_python_fuzz_printable_ascii():
    """Property test: random printable-ASCII keys/urls/refs stay content-identical.

    The fixture-based tests above pin specific inputs; this sweeps the whole
    printable-ASCII scalar domain in both key and value position. Scalars are kept
    short and space-free so the two sides also happen to render byte-identically,
    which isolates any quoting-decision drift from mere formatting differences.
    """
    rng = random.Random(20260701)
    printable = [chr(c) for c in range(0x20, 0x7F)]

    def rand(lo: int, hi: int) -> str:
        return "".join(rng.choice(printable) for _ in range(rng.randint(lo, hi)))

    for _doc in range(6):
        repositories = {}
        for _ in range(150):
            repositories[rand(1, 50)] = {  # key: 1..50 chars, non-empty, in-domain
                "url": rand(1, 50),  # non-empty -> truthy, no folding under 80 cols
                "ref": {"kind": "tag", "value": rand(1, 50)},
                "packages": {"pkg": {"tags": ["t"]}},
            }
        dist = {"schema_version": "2", "ros_distro": "jazzy", "repositories": repositories}
        _assert_same_content(_js_compose(dist, BASE), _py_compose(dist, BASE))
