# P3.35-R1 Native Typography Evidence Protocol

P3.35 moves the product focus from rare-feature expansion to common authoring fidelity.

Stage-one native matrix:

- character spacing: -50%, -20%, 0%, +20%, +100%
- font face applied to mixed Korean/Latin/Hanja text:
  - 함초롬바탕
  - 맑은 고딕
  - Times New Roman
- font size: 9pt and 13.5pt

The analyzer records, without assuming the answer in advance:

- run charPrIDRef;
- raw hh:charPr children;
- hh:spacing / hh:ratio / relSz / offset by script;
- fontRef across hangul/latin/hanja/japanese/other/symbol/user;
- fontface declarations and substitution children;
- charPr height and normalized point size;
- byte changes and package validity.

Production formatting mutation authority is unchanged during this evidence stage.

After native semantics are sealed, R1 continues with an implementation-generated mixed-run
fixture that combines Korean/Latin/Hanja segments with different font/size/spacing and
requires Hancom open/save to preserve run boundaries, text, and style assignment.
