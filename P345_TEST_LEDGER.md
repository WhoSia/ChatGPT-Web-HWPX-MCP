# P3.45 Test Ledger

## Phase

**ChatGPT Web HWPX MCP P3.45 — Document Transaction Runtime, Declarative Authoring IR, Incremental Recompilation, Deterministic Replay/Time-Travel, Capability Negotiation, Extension SDK & Production Observability**

## Architectural break

P3.45 moves high-level document work behind a runtime substrate instead of adding another flat family of Python tool handlers.

- **TypeScript** owns the declarative Authoring IR compiler, dependency DAG, capability negotiation, incremental invalidation/reuse rules, extension-manifest ABI, runtime transition machine and deterministic event creation.
- **Rust** independently verifies the append-only event hash chain, dependency ordering and legal node/run transitions. Production replay authority must come from this kernel.
- **Python** is a host adapter only: it binds selected IR node kinds to existing HWPX primitives and MCP persistence.
- **PowerShell/Hancom** remains external world contact; render evidence is never reconstructed by replay.

## Determinism

Deterministic event payloads use a JCS-compatible constrained JSON subset:
- object keys sorted;
- strings preserved;
- safe integers only;
- no floats/NaN/Infinity/undefined;
- timestamps and wall-clock latency excluded from the event hash.

Event hash:
`SHA256("p3.45-event-v1\0" + previous_hash + "\0" + seq + "\0" + canonical_event_body)`.

## Incremental recompilation

Only PURE nodes may be cache-reused. Document mutation and external-world-contact nodes are always re-executed/re-observed. Node-spec or provider-binding changes invalidate the node and all transitive dependents.

## Capability negotiation

Every node kind requires a named capability. Selection is deterministic and fail-closed for hard requirements. Additional providers/extensions may participate only through the frozen `p3.45-extension-v1` manifest ABI.

## Extension SDK boundary

P3.45 does **not** dynamically load arbitrary code. An extension manifest declares node kinds, capabilities, side-effect class and host-adapter identifier. Unknown/colliding node kinds and reusable mutation nodes are rejected.

## Observability

Deterministic runtime events and operational observation time are separate. Event names are low-cardinality lifecycle names; identifiers/hashes remain attributes. This follows the same separation used by modern event/trace telemetry without making OpenTelemetry itself a runtime dependency.

## Initial authority target

`DECLARATIVE_AUTHORING_IR_PASS / CAPABILITY_NEGOTIATION_PASS / PURE_NODE_INCREMENTAL_RECOMPILE_PASS / RUST_DETERMINISTIC_REPLAY_PASS / TIME_TRAVEL_INSPECTION_PASS / MANIFEST_EXTENSION_ABI_PASS / PRODUCTION_OBSERVABILITY_PASS`.

External world-contact replay and arbitrary extension code execution are explicit non-claims.


## Strengthened runtime invariants

P3.45 binds PURE-node reuse to the **base document revision**. A prior snapshot from revision N cannot be silently reused against revision N+1 merely because the node body is unchanged.

The TypeScript runtime rejects stale/tampered run seals before transition, time-travel, or observability. DOCUMENT_MUTATION commits must advance exactly one revision; PURE commits and external evidence preserve revision. External evidence is revision-bound and must explicitly carry measured world-contact validity.

The Rust replay kernel independently reconstructs and verifies:
- unique complete topological node inventory;
- action ↔ side-effect legality;
- dependency readiness at every node event;
- event sequence/hash/run-id custody;
- output and receipt hashes;
- mutation-vs-pure-vs-external revision deltas;
- materialized node states, outputs, current revision, and status;
- terminal `COMPLETED / ABORTED` semantics and absence of post-terminal events.

## Interruption and idempotency

Deterministic compilation is idempotent for an already stored identical run. A run-id/plan collision fails closed.

An interrupted RUNNING mutation is never assumed committed. The runtime exposes explicit **abort_document_transaction** only while durable revision custody still matches; revision divergence requires explicit reconciliation instead of silent rollback/commit inference.

## Developer SDK

`contracts/p345_extension_sdk.ts` exposes manifest builders for PURE, DOCUMENT_MUTATION, and EXTERNAL_WORLD_CONTACT nodes. Extension manifests materialize deterministic capability providers during compilation, while the Python host still rejects adapters outside its allow-list.

**Manifest-only extension does not mean dynamic code loading.**

## Standards anchors

- RFC 8785 JSON Canonicalization Scheme is the canonical cryptographic-serialization anchor. P3.45 deliberately uses a stricter safe-integer subset.
- OpenTelemetry-style event modeling informs the separation of low-cardinality lifecycle event names from dynamic IDs/hashes in attributes. Operational observation time remains outside replay authority.

## Product integration gate

P3.45 closure requires the same TypeScript runtime and Rust verifier to be present in:
1. dedicated cross-runtime CI;
2. MCP persistence/adapter regression;
3. full OAuth lifecycle;
4. Docker release smoke;
5. exact-head production deployment.

Production packaging must include compiled TypeScript runtime JS and the Rust `p345-replay` binary; Python-only fallback is not an accepted P3.45 production state.
