// Frontend unit tests: src/lib/*.test.ts, transpiled with the project's own TypeScript.
import ts from "typescript";
import { execFileSync } from "node:child_process";
import { mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
const out = "node_modules/.cache/tests";
mkdirSync(out, { recursive: true });
const files = readdirSync("src/lib").filter((f) => f.endsWith(".ts"));
for (const f of files) {
  const js = ts.transpileModule(readFileSync(`src/lib/${f}`, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  }).outputText.replace(/from "(\.\/[^"]+)"/g, 'from "$1.mjs"');
  writeFileSync(`${out}/${f.replace(/\.ts$/, ".mjs")}`, js);
}
for (const f of files.filter((f) => f.endsWith(".test.ts")))
  execFileSync("node", [`${out}/${f.replace(/\.ts$/, ".mjs")}`], { stdio: "inherit" });
