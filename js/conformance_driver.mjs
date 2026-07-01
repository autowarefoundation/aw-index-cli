// Test-only bridge for tests/test_conformance.py. Reads a JSON object
// {"distribution": <dict>, "options": <composeReposFile opts>} from stdin and
// writes the composed `.repos` document to stdout verbatim, so pytest can diff
// it against the Python compose over identical inputs. Not part of the public API.

import { composeReposFile } from "./compose.mjs";

let input = "";
process.stdin.setEncoding("utf-8");
process.stdin.on("data", (chunk) => {
  input += chunk;
});
process.stdin.on("end", () => {
  const { distribution, options } = JSON.parse(input);
  process.stdout.write(composeReposFile(distribution, options || {}));
});
