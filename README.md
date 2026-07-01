# aw-index-cli

[![ci](https://github.com/autowarefoundation/aw-index-cli/actions/workflows/ci.yaml/badge.svg)](https://github.com/autowarefoundation/aw-index-cli/actions/workflows/ci.yaml)

`aw-index-cli` is the consumer CLI for the [autoware-index][index] registry. It
reads a distribution manifest (`distributions/<rosdistro>.yaml`) and composes a
[vcs2l][vcs2l] `.repos` file you can `vcs import` into a workspace.

The registry is **repository-keyed**: each entry is one repository with **exactly
one `ref`** and the packages it hosts. `compose` never selects a ref by Autoware
version; `--autoware` is header provenance only.

[index]: https://github.com/autowarefoundation/autoware-index
[vcs2l]: https://github.com/ros-infrastructure/vcs2l

## Install

With [pipx][pipx] (recommended for an isolated CLI):

```bash
pipx install aw-index-cli   # first install
pipx upgrade aw-index-cli   # update to the latest release
```

[pipx]: https://pipx.pypa.io/

## `compose`

Render a `.repos` file from a distribution. Select what you need by package,
repository, or tag — the distribution is fetched from GitHub by default, so no
registry checkout is required.

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

> [!TIP]
> Omitting all of `--packages`, `--repository`, and `--tags` composes the
> **entire** distribution — supported, but usually you want to name what you
> consume.

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

Entries are pure vcs2l — `type`/`url`/`version` only. Selected package names
live in the `# selected packages by repository:` header comment, not the YAML
body.

### How entries are composed

- **Entry keys are registry repository keys**, not URL basenames — also the
  directory `vcs import` clones into.
- **Filters are ANDed.** An unknown `--packages` name or `--repository` key is a
  hard error, never a silent empty result.
- **A monorepo collapses to one entry** at its single `ref`, however many of its
  packages match.

> [!CAUTION]
> A clone may include unregistered sibling packages the index makes no claims
> about. To build only what you asked for, pass the header-comment names to colcon:

```bash
colcon build --packages-up-to autoware_livox_tag_filter  # names from the header comment
```

### Key options

- `--rosdistro` (required): ROS distribution, e.g. `jazzy`.
- `--packages` / `--repository` / `--tags`: selection filters, ANDed; unknown
  names error.
- `--autoware`: informational only — recorded in the header, not a ref selector.
- `--registry-path`: read a local file or registry directory instead of GitHub.
- `--registry-repo` / `--registry-ref`: GitHub source repo (default
  `autowarefoundation/autoware-index`) and git ref (default `main`).
- `--repo-root` / `--name` / `--output`: where and under what name to write the
  `.repos` (default `<repo-root>/repositories/autoware-index.repos`).
- `--stdout`: print instead of writing a file.
- `--no-timestamp`: omit `generated_at` for byte-identical output.

## Commands

- `compose` — render a `.repos` file from a distribution.
- `check` — gate a composed `.repos` against the registry and sweep history.
- `list` — list registry packages with their latest validation status.

> [!IMPORTANT]
> There is deliberately no `import` command — pipe `compose` straight into vcs:

```bash
aw-index-cli compose --rosdistro jazzy --packages autoware_livox_tag_filter --stdout \
  | vcs import src
```

## `check`

Verify a composed `.repos` is still current: every repository at the registry's
ref, each package passing its latest sweep. Intended as a **CI gate** after
`vcs import`.

```bash
# Auto-discovers ./autoware-index.repos or ./*/autoware-index.repos; rosdistro is
# read from the file's header. Exit code is the gate.
aw-index-cli check

# Or point at a specific file.
aw-index-cli check --repos repositories/autoware-index.repos --rosdistro jazzy
```

Per repository it reports ref drift, removal from the registry, each package's
latest status (`pass`/`fail`/`—`) and the Autoware version tested, and — for
`branch` refs — whether the branch advanced past the last sweep.

- **Exit `0`** — all pass, no drift.
- **Exit `1`** — any failing validation, ref drift, or removed package (with
  `--strict`, also unvalidated packages or a branch that advanced since the sweep).
- **Exit `2`** — could not run (bad/missing `.repos`, registry load error).

Options mirror `compose`, plus `--data-ref` (default `data`), `--strict`, and
`--format {table,json}`.

> [!NOTE]
> The branch-drift check shells out to `git ls-remote`; if `git` is absent it is
> skipped and everything else still runs.

## `list`

Enumerate the packages registered for a distro with their latest sweep status —
discovery plus a health readout, without composing anything.

```bash
aw-index-cli list --rosdistro jazzy
aw-index-cli list --rosdistro jazzy --tags sensing --format json
```

Accepts the same selection filters as `compose`. Exit `0` normally; with
`--strict`, exit `1` if any selected package is failing or unvalidated; exit `2`
on a registry load error.

## License

Apache-2.0. See [LICENSE](LICENSE).
