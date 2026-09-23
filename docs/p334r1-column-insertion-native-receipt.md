# P3.34-R1 Native Column-Insertion Evidence Receipt

## Capture provenance

- Hancom executable: `Hwp.exe`
- Hancom product version: `13.0.0.3622` (Office 2024)
- Capture schema: `chatgpt-web-hwpx-mcp/p3.34-r1/hancom-manual-capture/v1`
- Four cases captured; zero skipped.
- Every target passed ZIP CRC and XML parse.
- Package entry count remained 11/11 in every source/target pair.

## Admitted native observations

### basic-left-1 — PASS

- table: 3x3 → 3x4
- table width: 54000 → 72000
- inserted logical column: 1
- inserted width: 18000
- inserted cells are blank
- pre-existing columns at/after the boundary shift right by one
- source SHA-256: `ac688bc871822c3e18917832160a9404ec61c75a871cd6ba4c673c2baef0107e`
- target SHA-256: `04bedbf11600a88105f1636c68fcb45c0c5ce9a000e86e876feeae354977b95a`

### nonuniform-right-1 — PASS

- source widths: 12000 / 18000 / 24000
- target widths: 12000 / 18000 / 18000 / 24000
- anchor: middle column
- native inserted width equals the anchor logical column width: 18000
- table width: 54000 → 72000
- inserted cells are blank
- source SHA-256: `5cc03a02e381195b360c8621a57dd8dac6b6c1ca6679bf290fc1070aeef5b451`
- target SHA-256: `8e34987c2def3c6b12e76da9b7eb4eaeb6f0b0c4523e3e1cb68a076749d9efba`

### merged-header-left-1 — PASS

- source merged header: colAddr 0, colSpan 2, cell width 36000
- insertion boundary is inside that horizontal span
- target merged header: colAddr 0, colSpan 3
- target merged cell `cellSz/@width` remains 36000
- table width: 54000 → 72000
- unmerged rows receive a blank 18000-wide cell
- source SHA-256: `dac45116a7ed7099940a84cd30b327c2e7911aba352ada6c5edf41ba736c716b`
- target SHA-256: `f3ccd62d8808aeec82318e7350c9f5ed385245d6ee262f958c3a71fb1f690b87`

## Rejected witness

### basic-right-2 — EXCLUDED FROM count>1 evidence

The manual instruction requested two columns to the right, but the captured file
contains only one additional logical column:

- colCnt: 3 → 4, not 5
- table width: 54000 → 72000
- exactly one blank 18000-wide column appears after the anchor
- source SHA-256: `e9af8449e9467d891997e0b689d8cd976b2d5b37e918fab8082d9fd376265fb9`
- target SHA-256: `21f6cdb1677cf6396c5cd279dd605cb19e3a1bbf6a145abbc67043a29af2cb11`

Therefore the witness is valid as another count=1 right-insertion specimen but
**invalid for count=2 semantics**. P3.34-R1 keeps `count > 1` fail-closed.

Hancom's current help states that the dialog's 줄/칸 수 is the number inserted
and supports up to 63, so the observed +1 does not certify a +2 operation.

## Count=1 semantic seal

For the bounded candidate:

1. LEFT boundary = anchor colAddr.
2. RIGHT boundary = anchor colAddr + 1.
3. Existing cells beginning at/after the boundary shift colAddr by +1.
4. A horizontal merge strictly crossing the boundary increases colSpan by +1
   and does not materialize an extra physical cell in that row.
5. Native evidence leaves that crossing merged cell's cellSz width unchanged.
6. Non-crossing rows receive one blank cell cloned from the same-row anchor
   column formatting.
7. New cell width equals the anchor logical column width.
8. Table-level width increases by that width.
9. New blank-cell paragraph id is 0 in all captured native targets.

## Authority

`COUNT1_LEFT_RIGHT_NATIVE_SEMANTICS_PASS / CANDIDATE_IMPLEMENTATION_ONLY`

Production edit authority remains closed until implementation-generated HWPX
files survive Hancom open/save and the inherited P3.33 delivery regression.
