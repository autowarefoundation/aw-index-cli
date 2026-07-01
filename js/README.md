# `js/` — browser-reusable composition

`compose.mjs` is a dependency-free ES module that reimplements aw-index-cli's
registry → vcstool `.repos` composition for JavaScript consumers — primarily the
[autoware-index](https://github.com/autowarefoundation/autoware-index) browse
site's "repos builder", which reuses it so the site and the CLI never fork the
transform.

## Source of truth

The Python package (`src/aw_index_cli/compose.py`) remains the reference.
`compose.mjs` mirrors it 1:1 and is pinned to it by
[`tests/test_conformance.py`](../tests/test_conformance.py), which runs both over
shared fixtures and asserts **byte-for-byte identical** `.repos` output (including
PyYAML's exact scalar quoting). If you change one, change the other; the
conformance job in CI fails on drift.

Keep `VERSION` in `compose.mjs` equal to `__version__` in
`src/aw_index_cli/__init__.py` (also asserted by the conformance test).

## API

```js
import { composeReposFile, composeCommand } from "./compose.mjs";

// distribution: the parsed distributions/<distro>.yaml shape
//   { repositories: { <repoKey>: { url, ref: {kind, value}, packages: {<name>: {tags}} } } }
const reposText = composeReposFile(distribution, {
  rosDistro: "jazzy",
  source: "autowarefoundation/autoware-index@main",
  packages: ["autoware_livox_tag_filter"], // selection filter (also recorded in the header)
  // omit generatedAt for deterministic output (equivalent to `--no-timestamp`)
});

const command = composeCommand({ rosDistro: "jazzy", packages: ["autoware_livox_tag_filter"] });
// -> "aw-index-cli compose --rosdistro jazzy --packages autoware_livox_tag_filter --stdout | vcs import src"
```

Lower-level exports (`selectRepositories`, `toReposEntries`, `provenanceHeader`,
`renderRepos`, `yamlScalar`) mirror the Python functions of the same names.

## Consuming from the browse site

The site vendors a **committed copy** at `site/compose.mjs`, pinned to a released
tag of this repo and guarded by a CI drift-check. It is not published to npm and
is not shipped in the Python wheel — it is consumed as a static ES module via
`<script type="module">`.

## Tests

```bash
node --test js/*.test.mjs   # unit tests (js/compose.test.mjs)
pytest tests/test_conformance.py   # Python ↔ JS parity (needs node)
```
