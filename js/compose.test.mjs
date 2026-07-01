// Unit tests for compose.mjs, run with Node's built-in test runner:
//   node --test js/
// Zero dependencies. The `.repos` body's byte-for-byte parity with the Python
// compose is additionally locked by tests/test_conformance.py.

import test from "node:test";
import assert from "node:assert/strict";

import {
  VERSION,
  ComposeError,
  yamlScalar,
  selectRepositories,
  toReposEntries,
  provenanceHeader,
  composeReposFile,
  composeCommand,
} from "./compose.mjs";

const sampleDistribution = () => ({
  schema_version: "2",
  ros_distro: "jazzy",
  repositories: {
    "zeta-stack": {
      url: "https://github.com/example/zeta_stack",
      ref: { kind: "sha", value: "a".repeat(40) },
      packages: { zeta_pkg: { tags: ["perception"] } },
    },
    "alpha-mono": {
      url: "https://github.com/example/alpha_mono",
      ref: { kind: "branch", value: "main" },
      packages: {
        alpha_sensing: { tags: ["sensing"] },
        alpha_perception: { tags: ["perception"] },
      },
    },
    "mid-repo": {
      url: "https://github.com/example/mid_repo",
      ref: { kind: "tag", value: "v1.2.3" },
      packages: { mid_pkg: { tags: ["planning"] } },
    },
  },
});

const EXPECTED_BODY = `repositories:
  alpha-mono:
    type: git
    url: https://github.com/example/alpha_mono
    version: main
  mid-repo:
    type: git
    url: https://github.com/example/mid_repo
    version: v1.2.3
  zeta-stack:
    type: git
    url: https://github.com/example/zeta_stack
    version: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
`;

test("VERSION is a non-empty semver-ish string", () => {
  assert.equal(typeof VERSION, "string");
  assert.match(VERSION, /^\d+\.\d+\.\d+/);
});

test("yamlScalar matches PyYAML safe_dump quoting", () => {
  // [input, expected rendered scalar]. Expectations captured from PyYAML 6.x.
  const cases = [
    // plain: safe, and reloads as a string
    ["main", "main"],
    ["v1.2.3", "v1.2.3"],
    ["a".repeat(40), "a".repeat(40)],
    ["089", "089"],
    ["0o17", "0o17"],
    ["1e3", "1e3"],
    ["1.5e3", "1.5e3"],
    ["https://github.com/example/alpha_mono", "https://github.com/example/alpha_mono"],
    ["git", "git"],
    ["alpha-mono", "alpha-mono"],
    ["x:y", "x:y"],
    ["a:b:c", "a:b:c"],
    ["x---", "x---"],
    ["x...", "x..."],
    ["-x", "-x"],
    ["?x", "?x"],
    ["a,b", "a,b"],
    // quoted: would otherwise reload as a non-string
    ["1.20", "'1.20'"],
    ["1.0", "'1.0'"],
    ["yes", "'yes'"],
    ["no", "'no'"],
    ["true", "'true'"],
    ["false", "'false'"],
    ["on", "'on'"],
    ["off", "'off'"],
    ["null", "'null'"],
    ["~", "'~'"],
    ["", "''"],
    ["0x10", "'0x10'"],
    ["0b10", "'0b10'"],
    ["1_000", "'1_000'"],
    ["0755", "'0755'"],
    ["123", "'123'"],
    ["-5", "'-5'"],
    ["2026-01-01", "'2026-01-01'"],
    ["12:30", "'12:30'"],
    ["1:2:3", "'1:2:3'"],
    [".inf", "'.inf'"],
    [".nan", "'.nan'"],
    // quoted: trailing ':' and '---'/'...' document markers are block indicators
    ["foo:", "'foo:'"],
    ["bar:baz:", "'bar:baz:'"],
    ["---", "'---'"],
    ["...", "'...'"],
    ["---x", "'---x'"],
    ["...doc", "'...doc'"],
    // quoted: cannot be represented plain
    ["x: y", "'x: y'"],
    ["x #y", "'x #y'"],
    ["#x", "'#x'"],
    ["*x", "'*x'"],
    ["&x", "'&x'"],
    ["!x", "'!x'"],
    [" x", "' x'"],
    ["x ", "'x '"],
    ["%x", "'%x'"],
    ["@x", "'@x'"],
    ["[x]", "'[x]'"],
    ["{x}", "'{x}'"],
    ["|x", "'|x'"],
    [">x", "'>x'"],
    [",x", "',x'"],
    ["<<", "'<<'"],
    ["=", "'='"],
  ];
  for (const [input, expected] of cases) {
    assert.equal(yamlScalar(input), expected, `yamlScalar(${JSON.stringify(input)})`);
  }
});

test("selectRepositories: whole distribution, sorted, monorepo names sorted", () => {
  const selected = selectRepositories(sampleDistribution());
  assert.deepEqual(
    selected.map(([key, , names]) => [key, names]),
    [
      ["alpha-mono", ["alpha_perception", "alpha_sensing"]],
      ["mid-repo", ["mid_pkg"]],
      ["zeta-stack", ["zeta_pkg"]],
    ],
  );
});

test("selectRepositories: tag filter narrows to matching packages", () => {
  const selected = selectRepositories(sampleDistribution(), { tags: ["sensing"] });
  assert.deepEqual(
    selected.map(([key, , names]) => [key, names]),
    [["alpha-mono", ["alpha_sensing"]]],
  );
});

test("selectRepositories: packages filter is ANDed and by exact name", () => {
  const selected = selectRepositories(sampleDistribution(), { packages: ["mid_pkg", "zeta_pkg"] });
  assert.deepEqual(
    selected.map(([key]) => key),
    ["mid-repo", "zeta-stack"],
  );
});

test("selectRepositories: repository filter selects by registry key", () => {
  const selected = selectRepositories(sampleDistribution(), { repository: ["alpha-mono"] });
  assert.deepEqual(
    selected.map(([key, , names]) => [key, names]),
    [["alpha-mono", ["alpha_perception", "alpha_sensing"]]],
  );
});

test("selectRepositories: unknown names throw ComposeError", () => {
  assert.throws(
    () => selectRepositories(sampleDistribution(), { packages: ["nope"] }),
    ComposeError,
  );
  assert.throws(
    () => selectRepositories(sampleDistribution(), { repository: ["nope"] }),
    ComposeError,
  );
});

test("selectRepositories: empty 'packages' container is skipped, not an error", () => {
  // Mirrors Python's `... or {}`: a repo with `packages: []` (or `{}`) selects
  // nothing rather than raising, so it just drops out of the result.
  const dist = {
    repositories: {
      "empty-list": { url: "https://x/y", ref: { kind: "branch", value: "main" }, packages: [] },
      "empty-map": { url: "https://x/z", ref: { kind: "branch", value: "main" }, packages: {} },
      keep: {
        url: "https://x/w",
        ref: { kind: "branch", value: "main" },
        packages: { k: { tags: [] } },
      },
    },
  };
  assert.deepEqual(
    selectRepositories(dist).map(([key]) => key),
    ["keep"],
  );
  // A non-empty non-mapping is still a hard error (matches Python).
  assert.throws(
    () => selectRepositories({ repositories: { r: { packages: ["oops"] } } }),
    ComposeError,
  );
});

test("toReposEntries: missing url or ref.value throws", () => {
  assert.throws(
    () => toReposEntries([["r", { ref: { kind: "branch", value: "main" } }, ["p"]]]),
    ComposeError,
  );
  assert.throws(
    () => toReposEntries([["r", { url: "https://x/y", ref: { kind: "branch" } }, ["p"]]]),
    ComposeError,
  );
  // Empty 'ref' container coerces to {} then fails on the missing value, exactly
  // like Python's `spec.get("ref") or {}` — not a "ref is not a mapping" error.
  assert.throws(
    () => toReposEntries([["r", { url: "https://x/y", ref: [] }, ["p"]]]),
    /missing 'ref.value'/,
  );
});

test("composeReposFile: full document body matches PyYAML output", () => {
  const out = composeReposFile(sampleDistribution(), {
    rosDistro: "jazzy",
    source: "src",
    toolVersion: "0.1.0",
  });
  assert.ok(out.endsWith(EXPECTED_BODY), "body must match safe_dump byte-for-byte");
  assert.equal(out.split("\n")[0], "# aw-index-cli 0.1.0");
  assert.ok(out.includes("# rosdistro: jazzy\n"));
  assert.ok(out.includes("# selected packages by repository:\n"));
  assert.ok(out.includes("#   alpha-mono: alpha_perception, alpha_sensing\n"));
});

test("provenanceHeader: order and conditional lines", () => {
  const lines = provenanceHeader({
    toolVersion: "0.3.0",
    rosDistro: "jazzy",
    source: "autowarefoundation/autoware-index@main",
    packages: ["b", "a"],
    selection: [["r", ["a", "b"]]],
  });
  assert.equal(lines[0], "# aw-index-cli 0.3.0");
  assert.equal(lines[1], "# source: autowarefoundation/autoware-index@main");
  assert.equal(lines[2], "# rosdistro: jazzy");
  assert.equal(lines[3], "# tags: all");
  assert.equal(lines[4], "# packages: b, a");
  assert.equal(lines[5], "# selected packages by repository:");
  assert.equal(lines[6], "#   r: a, b");
  assert.ok(lines[lines.length - 1].startsWith("# Generated file"));
});

test("composeCommand: space-separated, sorted, with vcs import", () => {
  const cmd = composeCommand({ rosDistro: "jazzy", packages: ["mid_pkg", "alpha_sensing"] });
  assert.equal(
    cmd,
    "aw-index-cli compose --rosdistro jazzy --packages alpha_sensing mid_pkg --stdout | vcs import src",
  );
});

test("yamlScalar throws on non-printable-ASCII (fails loud, no silent divergence)", () => {
  // PyYAML would double-quote/escape these; this port refuses them instead of
  // emitting bytes that would differ from the Python composer.
  for (const bad of ["café", "naïve", "a\tb", "a\nb", "x\x7f", "\x00z", "π", "😀"]) {
    assert.throws(() => yamlScalar(bad), ComposeError, `yamlScalar(${JSON.stringify(bad)})`);
  }
  // The printable-ASCII boundary (0x20 space … 0x7E '~') stays in-domain.
  assert.equal(yamlScalar(" "), "' '");
  assert.equal(yamlScalar("~"), "'~'");
  assert.equal(yamlScalar("a~b"), "a~b");
});

test("composeReposFile rejects repository keys outside the inline simple-key domain", () => {
  const mk = (key) => ({
    repositories: {
      [key]: {
        url: "https://x/y",
        ref: { kind: "branch", value: "main" },
        packages: { p: { tags: ["t"] } },
      },
    },
  });
  const opts = { rosDistro: "jazzy", source: "src" };
  // A 122-char key is still emitted inline (matches PyYAML) …
  const key122 = "o/" + "r".repeat(120);
  assert.ok(composeReposFile(mk(key122), opts).includes(`  ${key122}:\n`));
  // … a 123-char key would trigger PyYAML's explicit `? key` form, so we refuse it.
  assert.throws(() => composeReposFile(mk("o/" + "r".repeat(121)), opts), ComposeError);
  // Empty key (PyYAML would emit `? ''`) is likewise refused.
  assert.throws(() => composeReposFile(mk(""), opts), ComposeError);
});

test("composeReposFile refuses values that would line-fold, but keeps long space-free values", () => {
  const mk = (value) => ({
    repositories: {
      "o/r": {
        url: "https://x/y",
        ref: { kind: "tag", value },
        packages: { p: { tags: ["t"] } },
      },
    },
  });
  const opts = { rosDistro: "jazzy", source: "src" };
  // A long value containing spaces would line-fold under PyYAML -> refuse.
  assert.throws(() => composeReposFile(mk("x ".repeat(60)), opts), ComposeError);
  // A long value with no spaces never folds (no break point) -> emitted inline.
  assert.doesNotThrow(() => composeReposFile(mk("v" + "1".repeat(200)), opts));
});
