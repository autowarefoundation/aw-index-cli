# aw-index-cli

`aw-index-cli` is the consumer CLI for the [autoware-index][index] registry. It
reads a distribution manifest (`distributions/<rosdistro>.yaml`,
`schema_version: "2"`) and composes a [vcstool][vcstool] `.repos` file that you
can `vcs import` into a workspace.

The registry is **repository-keyed**: each entry is a repository (identified by
a registry-unique key) carrying **exactly one `ref`** and one or more
registered packages. Ref skew between packages of the same repository is
unrepresentable by construction. The registry does *not* track Autoware
versions — those are resolved at sweep time, not stored. `compose` therefore
never selects a ref by Autoware version; the `--autoware` flag is recorded in
the header for provenance only.

[index]: https://github.com/autowarefoundation/autoware-index
[vcstool]: https://github.com/dirk-thomas/vcstool

## Install

With [pipx][pipx] (recommended for an isolated CLI):

```bash
pipx install aw-index-cli
```

Editable, from a checkout:

```bash
python3 -m pip install -e ".[dev]"
```

[pipx]: https://pipx.pypa.io/

## `compose`

Render a `.repos` file from a distribution.

```bash
# Compose the whole jazzy distribution from a local registry checkout,
# writing repositories/autoware-index.repos under the discovered repo root.
aw-index-cli compose --rosdistro jazzy \
  --registry-path /path/to/autoware-index

# Print to stdout instead of writing a file.
aw-index-cli compose --rosdistro jazzy \
  --registry-path /path/to/autoware-index --stdout

# Filter by tags and fetch the distribution from GitHub (no checkout needed).
aw-index-cli compose --rosdistro jazzy --tags sensing perception

# Fetch from a fork or a specific registry branch/tag/sha.
aw-index-cli compose --rosdistro jazzy \
  --registry-repo me/autoware-index-fork --registry-ref dev
```

Example output:

```yaml
# aw-index-cli 0.1.0
# source: local path /path/to/autoware-index
# rosdistro: jazzy
# tags: all
# generated_at: 2026-06-11T12:00:00+00:00
# selected packages by repository:
#   livox-tools: autoware_livox_decoder, autoware_livox_tag_filter
# Generated file — re-run 'aw-index-cli compose …' to update; do not edit by hand.
repositories:
  livox-tools:
    type: git
    url: https://github.com/autowarefoundation/autoware_livox_tag_filter
    version: main
```

Each entry is a pure vcstool entry — only `type`, `url`, and `version`. The
selected registered package names live in the `# selected packages by
repository:` header comment, not in the YAML body.

### How entries are composed

- **Entry keys are registry repository keys** (the keys under `repositories:`
  in the distribution YAML), not URL basenames. The key is also the checkout
  directory `vcs import` clones into.
- **A monorepo collapses to one clone.** A package is selected when `--tags`
  is empty or intersects its tags; a repository is selected when at least one
  of its packages is selected. However many of a repository's packages match,
  it yields exactly one `.repos` entry at the repository's single `ref`.
- **Entries are pure vcstool — `type`/`url`/`version` only.** The `.repos`
  format defines no other per-entry fields, so the selected registered package
  names are recorded in the `# selected packages by repository:` header comment
  (sorted by name), not in the YAML body. With a tag filter, that comment may
  name only a subset of a monorepo's registered packages. vcstool ignores
  comments, so `vcs import` works unchanged.
- **The clone may contain unregistered sibling packages** the index makes no
  claims about — registration is per package, but cloning is per repository.
  For a build scoped to what you actually asked for, pass the names from the
  header comment (or the registry) to colcon:

  ```bash
  colcon build --packages-up-to autoware_livox_tag_filter  # names from the header comment
  ```

- `version:` is the registry ref's `value` as-is; vcstool checks out tags,
  shas, and branches alike without needing to know the kind.

### schema_version gate

`compose` only accepts distribution documents with `schema_version: "2"`.
Anything else — older `"1"` documents, a missing field, or a future version —
aborts with a non-zero exit and a clear error naming the found version
("… not supported by this aw-index-cli (supports: '2')"). It never emits
silently empty output for a document it does not understand.

### Key options

- `--rosdistro` (required): ROS distribution, e.g. `jazzy`.
- `--tags ...`: keep only packages whose tags intersect these; omit for all.
- `--autoware`: informational only — recorded in the header, not a ref selector.
- `--registry-path`: local file or registry directory; omit to fetch from GitHub.
- `--registry-repo` / `--registry-ref`: GitHub source — the repository
  (default `autowarefoundation/autoware-index`) and the git ref (branch, tag,
  or sha; default `main`) of the registry to fetch the distribution from.
- `--repo-root`: where to discover `repositories/`; defaults to the current dir.
- `--name`: output basename (default `autoware-index`).
- `--output`: explicit output file path (overrides repo-root discovery).
- `--stdout`: print the rendered `.repos` instead of writing a file.
- `--no-timestamp`: omit `generated_at` for byte-identical, diffable output.

## Commands

- `compose` — render a `.repos` file from a distribution (implemented).
- `import` — *(not implemented yet)*
- `sync` — *(not implemented yet)*
- `check` — *(not implemented yet)*
- `refresh` — *(not implemented yet)*

## License

Apache-2.0. See [LICENSE](LICENSE).
