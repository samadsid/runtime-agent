import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const root = new URL("..", import.meta.url).pathname;
const targets = [join(root, "app"), join(root, "src")];
const violations = [];
function walk(directory) {
  for (const name of readdirSync(directory)) {
    const path = join(directory, name); const stat = statSync(path);
    if (stat.isDirectory()) { walk(path); continue; }
    if (!/\.tsx?$/.test(name) || /\.test\.tsx?$/.test(name) || path.includes("/src/test/")) continue;
    const rel = relative(root, path); const source = readFileSync(path, "utf8");
    if (!rel.startsWith("src/design-system/theme/") && /#[0-9a-fA-F]{3,8}\b/.test(source)) violations.push(`${rel}: raw color`);
    if (!rel.startsWith("src/design-system/") && source.includes("@expo/vector-icons")) violations.push(`${rel}: direct icon import`);
    if (source.includes("@/components/design-system")) violations.push(`${rel}: legacy design-system import`);
    if (/Dimensions\.get\(/.test(source)) violations.push(`${rel}: fixed Dimensions.get usage`);
  }
}
targets.forEach(walk);
if (violations.length) { console.error(violations.join("\n")); process.exit(1); }
console.log("UI static audit passed.");
