"""Conformance: ``js/compose.mjs`` must match the Python compose byte-for-byte.

The browse site reuses ``js/compose.mjs`` to build ``.repos`` files; this test is
the guarantee that the JS port cannot silently diverge from the reference Python
implementation. It runs both over identical inputs and asserts identical output.

Requires ``node`` on PATH (skipped otherwise); kept out of the pure-offline unit
suite's guarantees but runs in CI's dedicated conformance job.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest

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
    ],
)
def test_js_matches_python(sample_distribution, opts):
    merged = {**BASE, **opts}
    assert _js_compose(sample_distribution, merged) == _py_compose(sample_distribution, merged)


@pytest.mark.parametrize("opts", [{}, {"packages": ["on_pkg"]}])
def test_js_matches_python_adversarial_scalars(opts):
    merged = {**BASE, **opts}
    assert _js_compose(ADVERSARIAL, merged) == _py_compose(ADVERSARIAL, merged)


def test_js_version_matches_python():
    text = (JS_DIR / "compose.mjs").read_text(encoding="utf-8")
    match = re.search(r'export const VERSION = "([^"]+)";', text)
    assert match, "VERSION constant not found in compose.mjs"
    assert match.group(1) == __version__
