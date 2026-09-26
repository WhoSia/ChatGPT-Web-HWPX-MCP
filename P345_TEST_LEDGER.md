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
