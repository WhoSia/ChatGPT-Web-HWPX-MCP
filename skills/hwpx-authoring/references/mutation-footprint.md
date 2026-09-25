# Mutation Footprint & Preservation Authority

P3.42 makes preservation a measured package claim rather than a success flag.

## Required workflow

1. Before a bounded repair, keep the declared semantic/locator plan.
2. Execute **apply_document_design_repairs** through the P3.42 wrapper.
3. Inspect the returned `mutation_footprint`.
4. Require the preservation grade appropriate to the operation.
5. If `divergence.count > 0`, do not reinterpret the write as targeted preservation.
6. Render/human-review claims remain separate even when package-part preservation passes.

## Preservation grades

- `PACKAGE_IDENTICAL`: the whole HWPX container SHA-256 is identical.
- `TARGETED_PARTS_ONLY`: every observed changed/added/removed payload part is inside the exact declared scope, and every untouched common-part payload is byte-identical.
- `PACKAGE_VALID_ONLY`: the archives were inspectable but exact targeted preservation was not established.

The order is strongest to weakest:

`PACKAGE_IDENTICAL > TARGETED_PARTS_ONLY > PACKAGE_VALID_ONLY`.

A repair normally targets `TARGETED_PARTS_ONLY`; requiring `PACKAGE_IDENTICAL` for a real mutation would be contradictory.

## What is measured

The certificate separates:

- whole-package SHA-256;
- per-part uncompressed payload SHA-256;
- changed / added / removed part sets;
- unexpected changed / added / removed parts;
- required changes that failed to occur;
- untouched common-part payload identity;
- ZIP record-metadata drift for untouched parts.

ZIP record metadata is not silently equated with payload identity. Timestamp/compression metadata drift can be reported without downgrading `TARGETED_PARTS_ONLY` unless the caller explicitly requires record-metadata identity.

## Exact-scope rule

Expected scope accepts exact package paths only. Wildcards and path traversal are rejected. A broad pattern such as `Contents/*.xml` is not a preservation claim.

For P3.40 design repair, P3.42 reconstructs the expected package-part set from durable paragraph/table locators before mutation. Unexpected package-part change blocks the atomic commit.

## Durable-revision audit

Use **certify_document_revision_mutation_footprint** to compare two retained owned revisions when the expected scope is independently known. This is an audit/readback path; it does not retroactively prove that an operation was safe if the expected scope was invented after seeing the diff.

## Evidence boundary

A `TARGETED_PARTS_ONLY` PASS says nothing by itself about:

- visual improvement;
- semantic correctness inside a changed part;
- Hancom-native rendering fidelity;
- human aesthetic approval.

Use [evidence authority](evidence-authority.md) for those layers.
