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

Because the first structural byte census was executed before the split was sealed, the current HOLDOUT is explicitly **STRUCTURAL_CENSUS_EXPOSED** rather than a strict prospective holdout. R1 engineering priorities are therefore derived only from the DISCOVERY split. A fresh prospective holdout must be acquired in the next data batch before design-heuristic validation.

## First census
37/38 sources expose ordinary parseable XML. One source (`mX5JRNtRfUwZ`) is held as `PARSER_HOLD_OPAQUE_XML_PAYLOAD`; this is a compatibility gap, not proof that the source is malformed.

The all-source structural baseline has 37 parseable sources: tables 37/37, images 22/37, median table-text share 0.364, and median native heading-metadata share 0. This baseline is descriptive only.

The **primary R1 engineering census** uses DISCOVERY only: 21/22 parseable sources (the opaque source is in DISCOVERY), tables 21/21, images 13/21, median table-text share 0.3842, median bold share 0.1417, median native heading-metadata share 0, and mean text-weighted alignment approximately JUSTIFY 0.7413, CENTER 0.1495, LEFT 0.0928, RIGHT 0.0164.

These observations motivate table-layout robustness, a separate presentation-role hypothesis layer, and opaque-payload compatibility work. They do **not** imply that table-heavy or conventional public-document styling is aesthetically preferable.

## Product-development rule
Every empirical style proposal must state which authority layer supports it. A polished Word/PDF-like design request may override observed public-document convention when native validity and user intent are preserved.
