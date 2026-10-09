# Architecture and package migration contract

## Ownership boundaries

| Location | Responsibility |
| --- | --- |
| `server.py`, `server_p2.py` | Stable MCP/OAuth host entrypoints; keep thin |
| `hwpx_mcp/interfaces/` | Public MCP tool registration / resource facades |
| `hwpx_mcp/orchestration/` | User workflows, previews, admission, approval, document agents |
| `hwpx_mcp/corpus/` | Regression corpus, intake, semantic/style discovery and registry |
| `hwpx_mcp/document/` | Native document structural parsing primitives |
| `hwpx_mcp/probes/` | External HWP world-contact CLI probes, separate from runtime APIs |
| `tests/` | Tests, no new top-level `test_*.py` |
| `scripts/` | Operational CLIs, native replay and release validation |
| `docs/` | Extended feature notes / design, not runtime modules |

`pXXX` source filenames are currently **compatibility identifiers**, not intended long-term domain-level APIs. Each refactor should move cohesive features first, rewrite references and eventually stabilize public names around documents, typography, layout, delivery, and custody. Do not perform a mass rename before identifying direct imports, dynamic imports, CLI invocations and test fixtures.

## P4.19 package migration

- Earlier work moved all 111 root tests to `tests/`, sixteen P3.17–P3.32 regression corpus modules to `hwpx_mcp/corpus/`, selected MCP facades into `hwpx_mcp/interfaces/`, and combined two P4.19 implementation files into `hwpx_mcp/orchestration/p419_product.py`.
- This PR also relocates the complete P3.35 family: six corpus/typography/registry/style modules into `hwpx_mcp/corpus/` and `p335_mcp` to `hwpx_mcp/interfaces/`, preserving distinct functions and replacing runtime, test and CLI imports.
- Four native HWP probes now live under `hwpx_mcp/probes/`; the original world-contact CI retains its real fixture tests and invokes the new package paths. `p39_textbox` is under `hwpx_mcp/document/` with its runtime and corpus importers updated.
- Four bounded P3.34 native-document operations (rare-feature policy, column insertion, tracked-change resolution and existing-object group/ungroup) now live in `hwpx_mcp/document/` with distinct module identities. Runtime, scripts, tests and lazy imports use the packaged paths; this does not retire any feature.
- Python implementation merging is appropriate for truly cohesive responsibilities only. Distinct native features must keep independent testable interfaces even when stored in a shared package.
- The Python root-count budget is a **guardrail**, not proof that runtime functionality improved; every move also needs import/link audit, full tests, Docker import, and supported public tool discovery.

## Integration rules

1. All code writes target the actual PR head; check expected commit SHA before advancing it. Do not rewrite or delete branches.
2. Preserve owned-document authentication, CAS revision checks, encrypted custody and independent human approval during refactors. No approval or mutation from a client-side draft.
3. Update imports, direct module paths, tests, CI watch patterns, CLI invocations and Docker copies together; fail closed on stale imports.
4. Use `python scripts/p419_layout_audit.py` and full CI on the **same exact head** before changing release authority.
5. Historical code is only retired after proving it is genuinely unused; preserve source/evidence in Drive or Git history without claiming an archive is a runtime substitute.
6. Actions must not author commits as `github-actions[bot]`. Deploying production is a distinct human-controlled step.

## Native fidelity vs product-level acceptance

`STRUCTURAL_VALIDITY != VISUAL_FIDELITY`

`DURABLE_COMMIT != CONSUMER_VERIFIED_DELIVERY`

`STAGING != HUMAN_APPROVAL`

The release gate must report these separately and must not silently downgrade a held guarantee.
