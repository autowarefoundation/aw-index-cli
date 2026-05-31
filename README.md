# aw-index-cli

`aw-index-cli` is the consumer CLI for the [autoware-index][index] registry. It
reads a distribution manifest (`distributions/<rosdistro>.yaml`) and composes a
[vcstool][vcstool] `.repos` file that you can `vcs import` into a workspace.

The registry tracks **exactly one `ref` per (package, distribution)**. It does
*not* track Autoware versions — those are resolved at sweep time, not stored.
`compose` therefore never selects a ref by Autoware version; the `--autoware`
flag is recorded in the header for provenance only.

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
```

Example output:

```yaml
# aw-index-cli 0.1.0
# source: local path /path/to/autoware-index
# rosdistro: jazzy
# tags: all
# generated_at: 2026-05-31T12:00:00+00:00
# Generated file — re-run 'aw-index-cli compose …' to update; do not edit by hand.
repositories:
  autoware_livox_tag_filter:
    type: git
    url: https://github.com/autowarefoundation/autoware_livox_tag_filter
    version: main
```

### Key options

- `--rosdistro` (required): ROS distribution, e.g. `jazzy`.
- `--tags ...`: keep only packages whose tags intersect these; omit for all.
- `--autoware`: informational only — recorded in the header, not a ref selector.
- `--registry-path`: local file or registry directory; omit to fetch from GitHub.
- `--registry-repo` / `--registry-ref`: GitHub source (defaults
  `autowarefoundation/autoware-index` @ `main`).
- `--repo-root`: where to discover `repositories/`; defaults to the current dir.
- `--name`: output basename (default `autoware-index`).
- `--output`: explicit output file path (overrides repo-root discovery).
- `--stdout`: print the rendered `.repos` instead of writing a file.

## Commands

- `compose` — render a `.repos` file from a distribution (implemented).
- `import` — *(not implemented yet)*
- `sync` — *(not implemented yet)*
- `check` — *(not implemented yet)*
- `refresh` — *(not implemented yet)*

## License

Apache-2.0. See [LICENSE](LICENSE).
