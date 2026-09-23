# P3.34-R1 Implementation-Generated Hancom Round-Trip Receipt

## Scope

This receipt closes the final native-acceptance gate for the bounded
`insert_column_native_bounded` operation after the Hancom-native semantics
capture had already established count=1 LEFT/RIGHT behavior.

Hancom product version: `13.0.0.3622`.

## Implementation-generated specimens

### candidate-basic-left-1 — PASS

- before SHA-256: `8967329da6962951a9a85538465f385842c4977636c64ffe02ccb03218c99d46`
- after Hancom Ctrl+S SHA-256: `0e0118289e7b557418f96894c54aac4048c65064264df1dbc21a8d26cb988107`
- byte-identical: no
- ZIP entries: 11 → 11
- CRC: pass
- XML parse: pass
- logical table: 3x4 → 3x4
- all cell addresses, spans, sizes, and text preserved exactly

### candidate-nonuniform-right-1 — PASS

- before SHA-256: `40c6c4c9bac425d69f2b541a69b3f65b228b4e17b7c2a9ddf5d22bb361c2f890`
- after Hancom Ctrl+S SHA-256: `40c6c4c9bac425d69f2b541a69b3f65b228b4e17b7c2a9ddf5d22bb361c2f890`
- byte-identical: yes
- ZIP entries: 11 → 11
- CRC: pass
- XML parse: pass
- logical table: 3x4 → 3x4
- widths remain `12000 / 18000 / 18000 / 24000`
- all addresses/spans/text preserved exactly

### candidate-merged-left-1 — PASS

- before SHA-256: `80a439821f36c38f86647e7ca73929bfad2c91f6e32cb7dbf457c682022425c1`
- after Hancom Ctrl+S SHA-256: `96d1100aec68ab297e99bbf2759bf815cb8062996370440c97895d6fae5ff24b`
- byte-identical: no
- ZIP entries: 11 → 11
- CRC: pass
- XML parse: pass
- logical table: 3x4 → 3x4
- merged header remains `colAddr=0 / colSpan=3 / width=36000`
- all other cell geometry and text preserved exactly

## Promotion decision

The implementation-generated files are accepted by Hancom and survive a native
open/save cycle without semantic or structural drift. Combined with the
earlier native before/after capture, this closes:

- semantic contract;
- structural fixtures;
- native open/resave evidence;
- family regression;
- inherited production OAuth/Docker and P3.33 file-delivery regression.

Production authority is promoted to:

`COUNT1_LEFT_RIGHT_NATIVE_COLUMN_INSERTION`

through the existing revision-guarded `apply_advanced_table_edits` transaction
using operation `insert_column_native_bounded`.

## Explicit holds

- `count > 1`: NATIVE_EVIDENCE_MISMATCH / fail closed
- vertical merge involvement: NOT_IN_NATIVE_GOLD / fail closed
- nested tables: OUT_OF_SCOPE / fail closed
- legacy `insert_column_by_clone`: superseded and remains refused

## Verdict

**IMPLEMENTATION_GENERATED_HANCOM_ROUNDTRIP_PASS /
COUNT1_LEFT_RIGHT_NATIVE_COLUMN_INSERTION_PRODUCTION_AUTHORITY**
