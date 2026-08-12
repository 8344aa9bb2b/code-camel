import { cpSync, existsSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const src = join(root, "node_modules", "monaco-editor", "min", "vs");
const dest = join(root, "app", "static", "vendor", "monaco", "vs");

if (!existsSync(src)) {
  console.error("monaco-editor not installed; run `npm install` first.");
  process.exit(1);
}

rmSync(join(dest, ".."), { recursive: true, force: true });
cpSync(src, dest, { recursive: true });
console.log("Copied monaco-editor AMD build to app/static/vendor/monaco/vs");