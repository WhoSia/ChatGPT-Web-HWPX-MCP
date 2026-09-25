const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const compiled = path.join(root, ".tmp", "p341-ts", "p341_page_composition.js");
const fixture = path.join(root, "benchmarks", "p341_page_geometry_golden.tsv");
const { analyzePagePrimitive } = require(compiled);

const lines = fs.readFileSync(fixture, "utf8").trimEnd().split(/\r?\n/);
const header = lines.shift().split("\t");
let checked = 0;

for (const line of lines) {
  if (!line.trim()) continue;
  const cols = line.split("\t");
  const row = Object.fromEntries(header.map((key, i) => [key, cols[i] ?? ""]));
  const primitive = {
    width: Number(row.width),
    height: Number(row.height),
    line_count: Number(row.line_count),
    left: Number(row.left),
    right: Number(row.right),
    top: Number(row.top),
    bottom: Number(row.bottom),
    line_area: Number(row.line_area),
    largest_gap: Number(row.largest_gap),
    top_area: Number(row.top_area),
    bottom_area: Number(row.bottom_area),
  };
  const actual = analyzePagePrimitive(primitive, row.archetype).join(",");
  if (actual !== row.expected_codes) {
    throw new Error(`TypeScript parity failure for ${row.case}: expected '${row.expected_codes}', got '${actual}'`);
  }
  checked += 1;
}

if (checked === 0) throw new Error("No P3.41 golden fixtures were checked.");
console.log(JSON.stringify({ status: "PASS", runtime: "typescript", fixture_count: checked }));
