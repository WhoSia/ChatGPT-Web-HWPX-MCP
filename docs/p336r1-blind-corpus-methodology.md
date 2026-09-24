# P3.36-R1 Blind Corpus Methodology

P3.36-R1 treats collected public HWPX files as empirical evidence about Korean document-production conventions, not as aesthetic ground truth.

## Evidence layers
1. Native structure facts.
2. Observed public-document conventions.
3. Paired visual controls.
4. Explicit human design targets.

Prevalence can motivate compatibility and authoring features, but it cannot by itself define a preferred visual style.

## Blinding
Corpus sources are renamed to stable 12-character base62 pseudonyms. Original filenames, institutions, source families, and URLs remain in the provenance ledger and are excluded from blind analysis filenames. This is a blinding mechanism, not an anonymity or secrecy guarantee.

Exact HWPX/PDF pairs share a blind stem. Control-only PDFs receive independent stems.

## Split policy
Source groups are indivisible across DISCOVERY, CALIBRATION, and HOLDOUT. Near-identical attachments from one posting or document family must not cross split boundaries.

Batch 01 contains 38 admitted public HWPX:
- DISCOVERY: 22
- CALIBRATION: 8
- HOLDOUT: 8

## First census
37/38 sources expose ordinary parseable XML. One source (`mX5JRNtRfUwZ`) is held as `PARSER_HOLD_OPAQUE_XML_PAYLOAD`; this is a compatibility gap, not proof that the source is malformed.

Among the 37 parseable sources:
- tables occur in 37/37;
- images occur in 22/37;
- median table-text share is 0.364;
- median native heading-metadata share is 0;
- mean text-weighted alignment is approximately JUSTIFY 0.751, CENTER 0.162, LEFT 0.072, RIGHT 0.015.

These observations motivate table-layout robustness, a separate presentation-role hypothesis layer, and opaque-payload compatibility work. They do **not** imply that table-heavy or conventional public-document styling is aesthetically preferable.

## Product-development rule
Every empirical style proposal must state which authority layer supports it. A polished Word/PDF-like design request may override observed public-document convention when native validity and user intent are preserved.
