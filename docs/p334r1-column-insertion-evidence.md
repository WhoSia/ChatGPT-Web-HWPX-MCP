# P3.34-R1 — Table Column Insertion Native Evidence

## Objective

Establish the minimum Hancom-native contract needed to implement bounded column
insertion without guessing about grid addresses, merged spans, or width policy.

This phase does **not** promote column insertion merely because an XML mutation
can be written.

## Existing ancestry

The pinned `python-hwpx` table engine already understands the logical grid via
`cellAddr(rowAddr,colAddr)`, `cellSpan(rowSpan,colSpan)`, `cellSz`,
`rowCnt`, and `colCnt`. It already has structure-safe row cloning,
merged-grid validation, delete-column logic, and width derivation.

At the audited upstream head there is no independent insert-column primitive.

Hancom Help defines native column insertion relative to the current cell:
left/right, with an explicit count. A single-cell selection is the normal
dialog contract.

## Native gold matrix

1. `basic-left-1` — 3x3, insert 1 column left of the middle cell.
2. `basic-right-2` — 3x3, insert 2 columns right of the middle cell.
3. `merged-header-left-1` — first-row C1..C2 merged, insertion boundary passes
   through that horizontal span.
4. `nonuniform-right-1` — widths 12000/18000/24000 HWPUNIT, insert 1 column
   right of the middle cell.

## Questions that must be identified

The native targets must determine:

- how `colCnt` changes;
- which cells' `colAddr` shift;
- whether a `colSpan` crossing the insertion boundary grows;
- which neighboring cell supplies formatting for new cells;
- whether inserted cell content is blank;
- inserted-column `cellSz/@width` policy;
- whether existing widths are preserved or redistributed;
- whether table-level width changes;
- whether paragraph/object IDs are regenerated;
- which package entries change only because Hancom re-saved the file.

If any item remains ambiguous, the implementation stays evidence-gated.

## Windows/Hancom capture

Run from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/p334r1_run_hancom_column_capture.ps1
```

The runner creates the four source fixtures and opens a target copy one at a
time. For each case, perform only the printed Hancom table operation, save, and
close the window.

The runner then:

- rejects unchanged targets;
- records source/target SHA-256;
- checks ZIP CRC and XML parseability;
- extracts the first table's row/column counts, addresses, spans and cell sizes;
- records changed ZIP entries;
- writes `analysis-summary.json`;
- packages `artifacts/p334r1-column-insertion-pack-captured.zip`.

Upload that ZIP for adjudication.

## Promotion boundary

Native evidence is necessary but not sufficient. A future column-insertion
implementation must also pass family regression, OAuth/Docker, the P3.33
revision-bound HWPX delivery regression, and the periodic product UX guard
before editing authority changes.
