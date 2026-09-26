# P3.46 Test Ledger

## Phase

**ChatGPT Web HWPX MCP P3.46 — Typed Capability Kernel, Effect-Safe Tool Surface Projection, Contract/Schema Codegen, Sandboxed Extension Execution, Replay-Aware Developer Inspector, Runtime Diagnostics & Hot-Swappable Host Adapters**

## Architectural break

P3.46 turns the P3.45 transaction runtime into a developer platform instead of adding another flat document-feature family.

- **TypeScript** owns typed capabilities/effects, generated tool surfaces, contract codegen, the extension ABI, the replay-aware inspector, diagnostics and WASM ABI validation.
- **Rust** independently verifies effect-plan and tool-sequence legality before host execution.
- **Python** is limited to cross-runtime invocation, MCP binding and a compare-and-swap registry of pre-admitted HWPX host adapters.
- **P3.45 Rust replay authority remains intact.** P3.46 does not weaken its event-chain or revision invariants.

## Effect system

The shared vocabulary is:

READ_ONLY / PURE / DOCUMENT_MUTATION / RUNTIME_CONFIGURATION / EXTERNAL_WORLD_CONTACT / DELIVERY

RUNTIME_CONFIGURATION is intentionally distinct from DOCUMENT_MUTATION: switching a host-adapter profile must not pretend to advance an HWPX document revision.

Pre-execution rejection includes:
- reuse of effects other than READ_ONLY/PURE;
- action/effect mismatch;
- DELIVERY with downstream DAG dependents;
- DELIVERY before the end of a tool sequence;
- extension capability/tool/node collisions;
- executable extension effects other than PURE.

## Contract and tool-surface generation

Every projected tool receives:
- one named capability;
- one effect type;
- read-only/destructive/open-world annotations;
- a JSON input schema;
- a deterministic contract SHA-256.

The generated bundle includes the complete effect vocabulary, capability catalog, node catalog and tool surface under one canonical hash.

## Sandboxed extension execution

Executable extensions use host ABI p3.46-extension-v1.

The admitted executable profile is deliberately narrow:
- deterministic WASM_NO_IMPORTS only;
- fixed p346_run export;
- SHA-256-bound module bytes;
- 64 KiB maximum module;
- bounded host timeout;
- separate Node process with a 64 MiB heap ceiling;
- zero WebAssembly imports, therefore zero filesystem/network/host-function imports;
- executable capabilities, nodes and tools are PURE-only;
- arbitrary in-process Python/TypeScript extension loading remains forbidden.

This is a bounded computation extension boundary, not a general WASI plugin host.

## Replay-aware inspector and diagnostics

The inspector consumes only a P3.45 state that has already passed the existing Rust replay verifier, then exposes:
- transaction DAG and topological order;
- effect/action/node state;
- transitive invalidation and reuse;
- provider and adapter bindings;
- provider-binding hashes;
- event-chain hashes;
- output and host-receipt hashes;
- base/current revision and run state.

Inspection and diagnostics are read-only and never restore or mutate historical document state.

## Hot-swappable host adapters

The Python registry admits profiles only at process bootstrap.

Initial profiles:
- p3.45-compat;
- p3.46-guarded.

The guarded profile independently checks adapter revision deltas. Profile switches use a generation compare-and-swap token and explicit rollback. There is no runtime API for registering arbitrary Python code.

## Initial authority target

TYPED_CAPABILITY_KERNEL_PASS / EFFECT_SAFE_TOOL_PROJECTION_PASS / CONTRACT_SCHEMA_CODEGEN_PASS / RUST_EFFECT_INVARIANT_PASS / PURE_WASM_SANDBOX_PASS / REPLAY_AWARE_INSPECTOR_PASS / STRUCTURED_RUNTIME_DIAGNOSTICS_PASS / HOST_ADAPTER_HOT_SWAP_ROLLBACK_PASS.

Product integration, Docker packaging, OAuth lifecycle and exact-head production deployment remain separate closure gates after this kernel passes dedicated CI.


## Adversarial audit repair — owner-scoped adapter configuration

A pre-closure tenancy audit found that the first CAS adapter registry was process-global. Although it admitted only two fixed profiles, an authenticated caller could change the profile used by another document's later transaction.

Repair:
- adapter selection/generation/history are now keyed by owned `document_id`;
- hot-swap and rollback require document ownership before configuration mutation;
- P3.45 passes its owned `document_id` into the P3.46 adapter resolver;
- untouched documents remain independently at guarded generation 1;
- OAuth write smoke mutates only its own generated document;
- unit tests prove document-A swaps do not change document-B state.

Required closure authority: `OWNER_SCOPED_ADAPTER_CONFIGURATION_PASS / CROSS_DOCUMENT_CONFIGURATION_NONINTERFERENCE_PASS`.
