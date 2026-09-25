const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const compiled = path.join(root, ".tmp", "p342-ts", "p342_evidence.js");
const fixture = path.join(root, "benchmarks", "p342_footprint_grade_golden.tsv");
const { classifyFootprintGrade } = require(compiled);

const lines = fs.readFileSync(fixture, "utf8").trimEnd().split(/\r?\n/);
const header = lines.shift().split("\t");
let checked = 0;

for (const line of lines) {
  if (!line.trim()) continue;
  const cols = line.split("\t");
  const row = Object.fromEntries(header.map((key, i) => [key, cols[i] ?? ""]));
  const actual = classifyFootprintGrade({
    package_identical: row.package_identical === "1",
    expected_declared: row.expected_declared === "1",
    unexpected_changed: Number(row.unexpected_changed),
    unexpected_added: Number(row.unexpected_added),
    unexpected_removed: Number(row.unexpected_removed),
    missing_required: Number(row.missing_required),
    untouched_record_metadata_changed: Number(row.record_drift),
    require_untouched_record_metadata: row.require_record_identity === "1",
  });
  if (actual !== row.expected_grade) {
    throw new Error(
      `P3.42 TypeScript parity failure for ${row.case}: expected ${row.expected_grade}, got ${actual}`,
    );
  }
  checked += 1;
}

if (checked === 0) throw new Error("No P3.42 footprint fixtures were checked.");
console.log(JSON.stringify({ status: "PASS", runtime: "typescript", fixture_count: checked }));
