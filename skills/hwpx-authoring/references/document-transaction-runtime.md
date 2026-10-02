# P3.45 Document Transaction Runtime

P3.45 moves multi-step authoring behind a deterministic runtime rather than adding more flat tool choreography.

## Language ownership

- **TypeScript** owns Authoring IR compilation, dependency ordering, capability negotiation, incremental invalidation, extension manifests, and runtime transitions.
- **Rust** independently verifies the append-only event chain, legal transitions, materialized node states, output receipts, revision deltas, and terminal status.
- **Python** is the HWPX host adapter and MCP persistence bridge only.
- **PowerShell/Hancom** remains external world contact.

## Runtime law

1. Compile declarative IR with **compile_document_transaction**.
2. PURE nodes may be reused only when their node-spec hash, provider binding, and base document revision still match.
3. DOCUMENT_MUTATION nodes always execute and must advance exactly one durable revision.
4. EXTERNAL_WORLD_CONTACT nodes always stop at `WAIT_EXTERNAL`; submit measured evidence with the exact current revision.
5. After interruption, never infer that an in-flight mutation committed. Inspect/reconcile explicitly or abort when durable revision custody still matches.
6. Use **replay_document_transaction** for read-only historical inspection. It is not document restore.
7. Observability timestamps and latency belong outside the deterministic hash chain.

## Capability and extension SDK

The host ABI is `p3.45-extension-v1`. TypeScript helpers live in `contracts/p345_extension_sdk.ts`.

An extension manifest can declare node kinds and capability evidence, but it cannot load code. The host must already admit the referenced adapter. A reusable extension node must be PURE.

Capability selection is deterministic, version/evidence constrained, and bound into the compiled-plan hash. Provider-binding drift invalidates the node and its dependents.

## Canonicalization and telemetry

Deterministic payload hashing follows RFC 8785 JSON Canonicalization Scheme discipline on a deliberately narrower safe-integer subset. Floats, NaN/Infinity and undefined values are rejected.

Runtime event names stay low-cardinality; run IDs, node IDs, hashes, and other dynamic values are attributes. Operational observation time is separate from replay authority.

## Non-claims

- Replay cannot recreate external world contact.
- A cached PURE result does not authorize reuse of a document mutation.
- Time travel does not restore document bytes.
- Extension manifests do not execute arbitrary code.
