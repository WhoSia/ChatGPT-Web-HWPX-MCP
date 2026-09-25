# Public Corpus Evidence & Design Generalization

P3.42 reuses the P3.35 corpus registry. It does not create a second corpus truth store.

## Probe → verdict → coverage

Every registered source is evaluated through named probes. Verdicts are:

- `PASS`
- `FAIL`
- `WITHHELD`
- `NOT_APPLICABLE`

A withheld or not-applicable source remains in the denominator.

Current probes include:

- `BYTES_ACQUIRED`
- `PACKAGE_VALID`
- `PARSER_READBACK`
- `ROLE_EVIDENCE`
- `REUSE_RIGHTS_EXPLICIT`
- `PDF_CONTROL_BYTES_INSPECTED`
- `STRUCTURAL_STYLE_GENERALIZATION`
- `VISUAL_STYLE_GENERALIZATION`

## No evidence promotion

The following implications are forbidden:

- public page listing ⇒ bytes acquired;
- bytes acquired ⇒ valid HWPX;
- valid HWPX ⇒ parser/readback success;
- parser success ⇒ role/design evidence;
- page access ⇒ redistribution permission;
- declared PDF renderer metadata ⇒ inspected PDF control;
- common corpus style ⇒ normative design rule.

## Denominator discipline

Source provenance and statistical votes are different.

- Every registered source stays visible in the source-level ledger.
- Exact-byte duplicates keep every provenance record.
- Exact-byte duplicates count once in style-distribution support.
- Metadata-only sources are not silently removed.
- Institution/family filters must remain explicit.

## Design generalization

Use **query_evidence_grounded_design_generalizations** only for descriptive candidates that satisfy explicit support thresholds.

The result may distinguish:

- `STRUCTURAL_NATIVE_XML_ONLY`
- `STRUCTURAL_PLUS_INSPECTED_PDF_CONTROL`

Neither class is an automatic authoring default. Selection remains explicit and downstream. Cross-institution support is stronger descriptive evidence than one institution repeating its own template, but still does not establish universal aesthetic superiority.

## Prospective public seed

`corpus/p342-public-corpus-metadata.json` freezes an official-page denominator before binary acquisition. The seed intentionally records `metadata_only`; CI fails if those page listings somehow acquire parser/render/design authority without an explicit evidence transition.

Binary acquisition, source-specific licensing validation, paired PDF control, and Hancom-native world contact are successor evidence operations, not assumptions.
