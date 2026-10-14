import assert from "node:assert/strict";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";

const root = fileURLToPath(new URL("../", import.meta.url));
const manifest = JSON.parse(readFileSync(resolve(root, "UPSTREAM.json"), "utf8"));
assert.equal(manifest.commit, "06a466935536f8c9bcacb2d5efc0fc021be1bdff");
for (const name of ["bash", "powershell", "read", "write", "edit", "grep", "find", "ls"]) {
  assert.equal(existsSync(resolve(root, `packages/coding-agent/src/core/tools/${name}.ts`)), false);
}
assert.equal(existsSync(resolve(root, "packages/coding-agent")), false);
assert.equal(existsSync(resolve(root, "packages/ai/src/providers")), false);
const metadata = JSON.parse(readFileSync(resolve(root, "package.json"), "utf8"));
assert.deepEqual(Object.keys(metadata.dependencies), ["typebox"]);
for (const version of Object.values({ ...metadata.dependencies, ...metadata.devDependencies })) {
  assert.match(version, /^\d+\.\d+\.\d+$/);
}
function inspect(directory) {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = resolve(directory, entry.name);
    if (entry.isDirectory()) inspect(path);
    else if (entry.name.endsWith(".ts")) {
      assert.doesNotMatch(readFileSync(path, "utf8"), /from ["']@earendil-works\//);
    }
  }
}
inspect(resolve(root, "packages"));
console.log("Pi source provenance, removed tools, local imports and pinned dependencies: OK");
