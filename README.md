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

Select what you need — by package name or by repository entry. The
distribution is fetched from GitHub by default, so no registry checkout is
required.

```bash
# Recommended: compose just the packages you want.
aw-index-cli compose --rosdistro jazzy \
  --packages autoware_livox_tag_filter

# …or pull in whole repository entries by their registry key.
aw-index-cli compose --rosdistro jazzy \
  --repository autoware_livox_tag_filter

# Narrow by tag (filters can be combined; they are ANDed).
aw-index-cli compose --rosdistro jazzy --tags sensing perception

# Print to stdout instead of writing a file.
aw-index-cli compose --rosdistro jazzy \
  --packages autoware_livox_tag_filter --stdout
```

> Omitting all of `--packages`, `--repository`, and `--tags` composes the
> **entire** distribution into one `.repos`. That is supported but rarely what
> you want — prefer naming the packages or repositories you actually consume.

Less common sources — a local registry checkout, or a fork / specific git ref:

```bash
# Read from a local registry checkout instead of GitHub.
aw-index-cli compose --rosdistro jazzy \
  --packages autoware_livox_tag_filter \
  --registry-path /path/to/autoware-index

# Fetch the distribution from a fork at a specific branch/tag/sha.
aw-index-cli compose --rosdistro jazzy \
  --packages autoware_livox_tag_filter \
  --registry-repo me/autoware-index-fork --registry-ref dev
```

Example output for `compose --rosdistro jazzy --repository livox-tools`
(a monorepo entry hosting two registered packages):

```yaml
# aw-index-cli 0.1.0
# source: autowarefoundation/autoware-index@main
# rosdistro: jazzy
# tags: all
# repository: livox-tools
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
- **Selection is by package, repository, or tag — ANDed.** A package survives
  when it passes every filter you give: `--packages` (name in the list),
  `--repository` (its entry's key in the list), and `--tags` (its tags
  intersect the list). Omit a filter to not constrain on it; omit all three to
  take the whole distribution. A `--packages` name or `--repository` key that
  does not exist anywhere in the distribution is a hard error, never a silent
  empty result.
- **A monorepo collapses to one clone.** A repository is selected when at least
  one of its packages survives the filters. However many of its packages match,
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
aborts with exit `2` and a clear error naming the found version
("… not supported by this aw-index-cli (supports: '2')"). It never emits
silently empty output for a document it does not understand.

### Key options

- `--rosdistro` (required): ROS distribution, e.g. `jazzy`.
- `--packages ...`: keep only these registered package names. Unknown names error.
- `--repository ...`: keep only these repository entries, by registry key.
  Unknown keys error.
- `--tags ...`: keep only packages whose tags intersect these; omit for all.
  Combined with `--packages`/`--repository`, the filters are ANDed.
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

- `compose` — render a `.repos` file from a distribution.
- `check` — gate a composed `.repos` against the registry and sweep history.
- `list` — list registry packages with their latest validation status.

The CLI owns **registry-domain** operations and leaves workspace/git work to
[vcstool][vcstool]. There is deliberately no `import` command — pipe `compose`
straight into vcs:

```bash
aw-index-cli compose --rosdistro jazzy --packages autoware_livox_tag_filter --stdout \
  | vcs import src
```

## `check`

Verify that a composed `.repos` is still in good standing: every repository at the
registry's current ref, and each registered package passing its latest sweep. Reads
the distribution (current refs) and the `data` branch's per-package validation
history. Intended as a **CI gate** after `vcs import`.

```bash
# Auto-discovers ./autoware-index.repos or ./*/autoware-index.repos; rosdistro is
# read from the file's header. Exit code is the gate.
aw-index-cli check

# Or point at a specific file.
aw-index-cli check --repos repositories/autoware-index.repos --rosdistro jazzy
```

Per repository it reports: **ref drift** (your pinned ref ≠ the registry's current
ref), **removed** (no longer registered), each package's latest **validation status**
(`pass`/`fail`/`—` unvalidated) and the Autoware version it was tested against, and —
for `branch` refs — whether the branch advanced past the last swept commit.

- **Exit `0`** — all checked packages pass, no drift.
- **Exit `1`** — any failing validation, ref drift, or removed package (with
  `--strict`, also unvalidated packages or a branch that advanced since the sweep).
- **Exit `2`** — could not run (bad/missing `.repos`, registry load error).

Key options: `--repos` (default: auto-discover), `--rosdistro` (default: from the
header), `--registry-path/--registry-repo/--registry-ref` (as `compose`),
`--data-ref` (default `data`), `--strict`, `--format {table,json}`. `check`'s
branch-drift check shells out to `git ls-remote`; if `git` is absent that check is
skipped (best-effort), everything else still runs.

## `list`

Enumerate the packages registered for a distro, annotated with their latest sweep
status — discovery plus a health readout, without composing anything.

```bash
aw-index-cli list --rosdistro jazzy
aw-index-cli list --rosdistro jazzy --tags sensing --format json
```

Accepts the same selection filters as `compose` (`--packages`, `--repository`,
`--tags`). Exit `0` normally; with `--strict`, exit `1` if any selected package is
failing or unvalidated; exit `2` on a registry load error.

## License

Apache-2.0. See [LICENSE](LICENSE).
