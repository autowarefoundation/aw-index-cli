// aw-index-cli — canonical registry→`.repos` composition, as an ES module.
//
// This mirrors `src/aw_index_cli/compose.py` 1:1 so a JavaScript consumer (the
// autoware-index browse site's "repos builder") can reuse the SAME transform
// instead of forking a second, drifting implementation. The Python CLI remains
// the reference; `tests/test_conformance.py` runs both this module and the
// Python compose over shared fixtures and asserts byte-for-byte identical
// `.repos` output, so the two cannot silently diverge.
//
// Dependency-free on purpose: no npm, no bundler. It is importable directly in
// the browser via `<script type="module">` and by Node's built-in test runner.

/** Keep equal to `src/aw_index_cli/__init__.py` `__version__` (asserted by conformance). */
export const VERSION = "0.3.0";

/** Registry defaults, mirroring `registry.py` `DEFAULT_REPO`/`DEFAULT_REF`. */
export const DEFAULT_REPO = "autowarefoundation/autoware-index";
export const DEFAULT_REF = "main";

/** Raised when a distribution cannot be composed into `.repos` entries. */
export class ComposeError extends Error {
  constructor(message) {
    super(message);
    this.name = "ComposeError";
  }
}

// Sort by code point, matching Python's `sorted()` on ASCII registry keys/names.
const cmp = (a, b) => (a < b ? -1 : a > b ? 1 : 0);

const isMapping = (v) => v !== null && typeof v === "object" && !Array.isArray(v);

// Mirror Python's `x or {}` for a `packages`/`ref` value: any empty or absent
// container (`null`/`undefined`/`[]`/`{}`) becomes an empty mapping, so an empty
// `packages: []`/`ref: []` selects nothing (Python) rather than raising. JS `[]`
// and `{}` are truthy, so `|| {}` alone would not match Python here.
const mappingOrEmpty = (v) => {
  if (!v) return {};
  if (Array.isArray(v)) return v.length ? v : {};
  return v;
};

function rejectUnknown(singular, plural, missing) {
  if (missing.length) {
    const names = missing
      .slice()
      .sort(cmp)
      .map((n) => `'${n}'`)
      .join(", ");
    const label = missing.length === 1 ? singular : plural;
    throw new ComposeError(`no such ${label} in the distribution: ${names}`);
  }
}

/**
 * Return `[key, spec, selectedNames]` triples sorted by repo key.
 *
 * The three optional filters (`tags`, `packages`, `repository`) are ANDed;
 * omit all to select the whole distribution. An explicit `repository` key or
 * `packages` name absent from the *whole* distribution throws `ComposeError`
 * (so a typo never hides behind an empty result). Mirrors
 * `compose.select_repositories`.
 */
export function selectRepositories(
  distribution,
  { tags = null, packages = null, repository = null } = {},
) {
  const allRepos = (distribution && distribution.repositories) || {};
  const wantedTags = new Set(tags || []);
  const wantedPkgs = new Set(packages || []);
  const wantedRepos = new Set(repository || []);

  const knownPkgs = new Set();
  for (const spec of Object.values(allRepos)) {
    const specPkgs = spec && spec.packages;
    if (isMapping(specPkgs)) {
      for (const name of Object.keys(specPkgs)) knownPkgs.add(name);
    }
  }
  rejectUnknown(
    "repository entry",
    "repository entries",
    [...wantedRepos].filter((r) => !Object.hasOwn(allRepos, r)),
  );
  rejectUnknown(
    "package",
    "packages",
    [...wantedPkgs].filter((p) => !knownPkgs.has(p)),
  );

  const selected = [];
  for (const key of Object.keys(allRepos).sort(cmp)) {
    if (wantedRepos.size && !wantedRepos.has(key)) continue;
    const spec = allRepos[key] || {};
    const specPkgs = mappingOrEmpty(spec.packages);
    if (!isMapping(specPkgs)) {
      throw new ComposeError(
        `repository '${key}' has 'packages' that is not a mapping of package name to spec`,
      );
    }
    const names = Object.keys(specPkgs)
      .filter((name) => {
        const pkg = specPkgs[name] || {};
        const pkgTags = new Set((pkg && pkg.tags) || []);
        const tagOk = wantedTags.size === 0 || [...pkgTags].some((t) => wantedTags.has(t));
        const pkgOk = wantedPkgs.size === 0 || wantedPkgs.has(name);
        return tagOk && pkgOk;
      })
      .sort(cmp);
    if (names.length) selected.push([key, spec, names]);
  }
  return selected;
}

/**
 * Map selected repositories to an ordered `Map<key, {type,url,version}>`.
 *
 * The entry key is the registry repository key, so a monorepo's packages
 * collapse into one clone. Each entry carries exactly vcstool's
 * `type`/`url`/`version`; `version` is `ref.value` verbatim. Throws
 * `ComposeError` on missing `url`/`ref.value` or a non-mapping `ref`. Mirrors
 * `compose.to_repos_entries` (a Map preserves insertion order for every key).
 */
export function toReposEntries(repositories) {
  const entries = new Map();
  for (const [key, specRaw] of repositories) {
    const spec = specRaw || {};
    const url = spec.url;
    if (!url) throw new ComposeError(`repository '${key}' is missing 'url'`);
    const ref = mappingOrEmpty(spec.ref);
    if (!isMapping(ref)) {
      throw new ComposeError(
        `repository '${key}' has 'ref' that is not a mapping with 'kind' and 'value'`,
      );
    }
    const version = ref.value;
    if (!version) throw new ComposeError(`repository '${key}' is missing 'ref.value'`);
    entries.set(key, { type: "git", url, version });
  }
  return entries;
}

/**
 * Build the `# …` comment lines that precede the rendered `.repos`.
 * Mirrors `compose.provenance_header` — same order and the same conditional
 * gates (`autoware`/`generatedAt` on `!= null`; the rest on truthiness).
 */
export function provenanceHeader({
  toolVersion,
  rosDistro,
  source,
  tags = null,
  packages = null,
  repository = null,
  autoware = null,
  generatedAt = null,
  selection = null,
} = {}) {
  const lines = [
    `# aw-index-cli ${toolVersion}`,
    `# source: ${source}`,
    `# rosdistro: ${rosDistro}`,
    `# tags: ${tags && tags.length ? tags.join(", ") : "all"}`,
  ];
  if (packages && packages.length) lines.push(`# packages: ${packages.join(", ")}`);
  if (repository && repository.length) lines.push(`# repository: ${repository.join(", ")}`);
  if (autoware != null) {
    lines.push(
      `# autoware: ${autoware} (informational only — not a ref selector; the registry tracks one ref per repository)`,
    );
  }
  if (generatedAt != null) lines.push(`# generated_at: ${generatedAt}`);
  if (selection && selection.length) {
    lines.push("# selected packages by repository:");
    for (const [key, names] of selection) lines.push(`#   ${key}: ${names.join(", ")}`);
  }
  lines.push("# Generated file — re-run 'aw-index-cli compose …' to update; do not edit by hand.");
  return lines;
}

/**
 * Render the full `.repos` document (header comments + YAML body).
 * Mirrors `compose.render_repos`: `header.join("\n") + "\n" + body`, where the
 * body reproduces `yaml.safe_dump({"repositories": entries}, sort_keys=False,
 * default_flow_style=False)` exactly (see `dumpBody`/`yamlScalar`).
 */
export function renderRepos(
  distribution,
  { tags = null, packages = null, repository = null, headerLines } = {},
) {
  const repositories = selectRepositories(distribution, { tags, packages, repository });
  const entries = toReposEntries(repositories);
  return headerLines.join("\n") + "\n" + dumpBody(entries);
}

/** Provenance string mirroring `registry.describe_source` for the network default. */
export function defaultSource(repo = DEFAULT_REPO, ref = DEFAULT_REF) {
  return `${repo}@${ref}`;
}

/**
 * One-call convenience assembling header + body exactly like the CLI's
 * `compose` handler (`cli._cmd_compose`). `packages`/`tags`/`repository` are the
 * selection filters AND are recorded in the header, matching
 * `aw-index-cli compose …`. Omit `generatedAt` for deterministic output
 * (equivalent to `--no-timestamp`).
 */
export function composeReposFile(
  distribution,
  {
    rosDistro,
    source,
    toolVersion = VERSION,
    tags = null,
    packages = null,
    repository = null,
    autoware = null,
    generatedAt = null,
  } = {},
) {
  const src = source != null ? source : defaultSource();
  const selection = selectRepositories(distribution, { tags, packages, repository }).map(
    ([key, , names]) => [key, names],
  );
  const headerLines = provenanceHeader({
    toolVersion,
    rosDistro,
    source: src,
    tags,
    packages,
    repository,
    autoware,
    generatedAt,
    selection,
  });
  return renderRepos(distribution, { tags, packages, repository, headerLines });
}

/**
 * The exact `aw-index-cli compose …` command that reproduces a selection of
 * individually-picked packages. `--packages` is space-separated (`nargs="*"`).
 */
export function composeCommand({ rosDistro, packages = [] } = {}) {
  const names = [...new Set(packages)].sort(cmp);
  const pkgArg = names.length ? ` --packages ${names.join(" ")}` : "";
  return `aw-index-cli compose --rosdistro ${rosDistro}${pkgArg} --stdout | vcs import src`;
}

// ---------------------------------------------------------------------------
// YAML emission — faithful to PyYAML 6.x `safe_dump(default_flow_style=False)`.
// ---------------------------------------------------------------------------

// PyYAML's implicit resolver patterns (SafeLoader), ported verbatim with the
// re.X whitespace stripped. A plain scalar matching any of these would reload
// as a non-string, so it must be single-quoted to stay a string.
const RESOLVERS = [
  /^(?:yes|Yes|YES|no|No|NO|true|True|TRUE|false|False|FALSE|on|On|ON|off|Off|OFF)$/,
  /^(?:[-+]?0b[0-1_]+|[-+]?0[0-7_]+|[-+]?(?:0|[1-9][0-9_]*)|[-+]?0x[0-9a-fA-F_]+|[-+]?[1-9][0-9_]*(?::[0-5]?[0-9])+)$/,
  /^(?:[-+]?(?:[0-9][0-9_]*)\.[0-9_]*(?:[eE][-+][0-9]+)?|\.[0-9][0-9_]*(?:[eE][-+][0-9]+)?|[-+]?[0-9][0-9_]*(?::[0-5]?[0-9])+\.[0-9_]*|[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN))$/,
  /^(?:~|null|Null|NULL|)$/,
  /^(?:[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]|[0-9][0-9][0-9][0-9]-[0-9][0-9]?-[0-9][0-9]?(?:[Tt]|[ \t]+)[0-9][0-9]?:[0-9][0-9]:[0-9][0-9](?:\.[0-9]*)?(?:[ \t]*(?:Z|[-+][0-9][0-9]?(?::[0-9][0-9])?))?)$/,
  /^(?:<<)$/,
  /^(?:=)$/,
];

// Characters that can never begin a plain scalar (PyYAML `analyze_scalar`).
const LEADING_INDICATORS = new Set([
  " ",
  "#",
  ",",
  "[",
  "]",
  "{",
  "}",
  "&",
  "*",
  "!",
  "|",
  ">",
  "@",
  "`",
  '"',
  "'",
  "%",
]);

// Return the first character outside printable ASCII (0x20–0x7E), or null when
// the whole string is printable ASCII. PyYAML's `safe_dump` renders anything
// else with a style this dependency-free port deliberately does not reproduce:
// non-ASCII is double-quoted with `\xNN`/`\uNNNN` escapes (default
// `allow_unicode=False`) and control characters force a non-plain style. The
// registry's scalar domain (refs/SHAs/tags/branches/URLs and `org/repo` keys)
// is printable ASCII, so rather than emit bytes that would silently differ from
// the Python composer, `yamlScalar` rejects such input (see below).
function firstNonPrintableAscii(s) {
  for (let i = 0; i < s.length; i += 1) {
    const c = s.charCodeAt(i);
    if (c < 0x20 || c > 0x7e) return s[i];
  }
  return null;
}

// Precondition: `s` is non-empty printable ASCII (`yamlScalar` rejects anything
// else). True when PyYAML could not render `s` as a *plain* block scalar and so
// must single-quote it.
function needsPlainQuoting(s) {
  const first = s[0];
  if (LEADING_INDICATORS.has(first)) return true;
  // '-', '?', ':' are indicators only when followed by a space or at end.
  if ((first === "-" || first === "?" || first === ":") && (s.length === 1 || s[1] === " ")) {
    return true;
  }
  // A ':' that ends the scalar (or precedes a space) is a block indicator.
  if (s[s.length - 1] === ":" || s.includes(": ")) return true;
  if (s.startsWith("---") || s.startsWith("...")) return true;
  if (s[s.length - 1] === " ") return true;
  if (s.includes(" #")) return true;
  return false;
}

/**
 * Render one scalar as PyYAML's `safe_dump` would: plain when it is safe and
 * reloads as a string, otherwise single-quoted (with `'` doubled). This is the
 * one subtle piece — e.g. a numeric-looking tag `1.20`, or a branch `on`/`no`,
 * must be quoted so it round-trips as a string. Exported for unit testing.
 *
 * Faithful to `safe_dump` over the registry's scalar domain — printable ASCII
 * refs/SHAs/tags/branches/URLs and `org/repo` keys. It does NOT reproduce the
 * double-quoted style `safe_dump` uses for non-ASCII (default
 * `allow_unicode=False`) or control characters — but rather than silently emit
 * bytes that would differ from the Python composer, it throws `ComposeError` on
 * such input. Neither can occur in the registry's scalar domain.
 */
export function yamlScalar(value) {
  const s = String(value);
  const bad = firstNonPrintableAscii(s);
  if (bad !== null) {
    const cp = bad.codePointAt(0).toString(16).toUpperCase().padStart(2, "0");
    throw new ComposeError(
      `cannot render scalar ${JSON.stringify(s)}: character U+${cp} is outside ` +
        `this composer's printable-ASCII domain; PyYAML would escape or requote ` +
        `it and the output would diverge from the Python composer`,
    );
  }
  if (s === "") return "''";
  if (RESOLVERS.some((re) => re.test(s)) || needsPlainQuoting(s)) {
    return `'${s.replace(/'/g, "''")}'`;
  }
  return s;
}

// Emit one `    <name>: <scalar>` value line. PyYAML `safe_dump` line-folds a
// plain/single-quoted scalar at a space once the line passes best_width (80
// columns); this port does not reproduce folding, so — like the other domain
// guards — it fails loud rather than silently diverging. The refusal condition
// (contains a space AND the line exceeds 80 columns) covers every value PyYAML
// would fold and never refuses one it would not fold below 80 columns. Only
// *values* can fold — block-mapping keys are always written unfolded — and a
// real url/version (URL, git ref, SHA) never contains a space, so this never
// fires for well-formed registry data.
function dumpField(name, value) {
  const line = `    ${name}: ${yamlScalar(value)}`;
  if (String(value).includes(" ") && line.length > 80) {
    throw new ComposeError(
      `${name} value ${JSON.stringify(value)} would line-fold under PyYAML ` +
        `safe_dump (its line exceeds 80 columns and contains a space), a wrap this ` +
        `composer does not reproduce; the output would diverge from the Python ` +
        `composer`,
    );
  }
  return line + "\n";
}

// Reproduce `yaml.safe_dump({"repositories": entries})` for our fixed shape:
// a `repositories:` mapping keyed by repo key, each value a 3-field mapping.
function dumpBody(entries) {
  if (entries.size === 0) return "repositories: {}\n";
  let out = "repositories:\n";
  for (const [key, entry] of entries) {
    // PyYAML emits a mapping key with the explicit `? key` / `: value` block
    // form (not inline `key:`) when the key is empty or its length reaches the
    // 128-char simple-key limit (raw length >= 123 here). This port only emits
    // the inline form, so it refuses those keys rather than silently diverging.
    // Real `org/repo` keys are non-empty and far shorter than 123 characters.
    if (key.length === 0 || key.length >= 123) {
      throw new ComposeError(
        `repository key ${JSON.stringify(key)} (length ${key.length}) is outside ` +
          `this composer's inline simple-key domain; PyYAML would emit it with the ` +
          `explicit '? key' block form and the output would diverge from the ` +
          `Python composer`,
      );
    }
    out += `  ${yamlScalar(key)}:\n`;
    out += dumpField("type", entry.type);
    out += dumpField("url", entry.url);
    out += dumpField("version", entry.version);
  }
  return out;
}
