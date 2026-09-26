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


## Sandbox resource hardening

The initial no-import WASM boundary still allowed a module to declare internal linear memory or tables. V8's old-space limit does not by itself constitute a reliable bound on WebAssembly linear memory, so the scalar extension ABI is narrowed further.

- reject WASM table, memory, element, data and data-count sections before module instantiation;
- retain zero imports and the fixed `p346_run -> safe integer` result contract;
- record `linear_memory=false` and `tables=false` in execution receipts;
- let the Python parent process own the kill timeout, derived from the manifest timeout plus bounded process-startup grace;
- add a valid-but-memory-declaring module as a negative control.

Required closure authority: `PURE_SCALAR_WASM_RESOURCE_BOUNDARY_PASS / PARENT_PROCESS_TIMEOUT_PASS`.


## Contract-derived tool composition

Effect-only validation remains available as the low-level invariant API, but callers no longer need to self-report effects when validating the projected MCP surface.

- projected tool-name sequences resolve capability/effect from the authoritative TypeScript inventory;
- projected tool-call DAGs derive an effect plan from tool contracts before Rust verification;
- caller-supplied effect or capability overrides are rejected on divergence;
- unknown projected tools fail closed;
- the derived effect plan is independently checked by the Rust guard.

Required closure authority: `CONTRACT_DERIVED_TOOL_EFFECT_PASS / CALLER_EFFECT_SPOOF_REJECTION_PASS`.


## Run-local adapter binding and replay-preserving host receipt sidecar

A second adapter audit found that document-scoped configuration alone did not guarantee **one adapter binding per transaction run**. A document profile could be switched between two node executions, or a process restart could lose an in-memory run binding.

Repair:
- the first host-adapter resolution for a `(document_id, run_id)` pins `(profile, generation)`;
- later nodes in the same run ignore subsequent document-level profile changes;
- previously committed host nodes persist a **hash-only P3.46 receipt sidecar** outside the sealed P3.45 runtime state;
- after process restart, the next node recovers its run binding from that sidecar before adapter execution;
- contradictory persisted bindings fail closed before further host execution;
- the P3.46 inspector joins the replay-verified P3.45 state with sidecar provenance and checks sidecar seal, node identity, runtime receipt hash, generation validity and within-run configuration drift;
- legacy P3.45 runs with no sidecar remain valid and produce no synthetic provenance.

Required closure authority:
`RUN_LOCAL_ADAPTER_BINDING_PASS / RESTART_BINDING_RECOVERY_PASS / REPLAY_PRESERVING_HOST_RECEIPT_SIDECAR_PASS / ADAPTER_CONFIGURATION_DRIFT_DIAGNOSTIC_PASS`.


### Pre-execution sidecar trust rule

Persisted adapter provenance is never trusted merely because it is stored in document metadata. Before it may re-pin a resumed run, P3.45 now verifies the P3.46 provenance seal, node identity and the sidecar receipt hash against the Rust-replay-verified runtime output. A mismatch stops the next host adapter **before execution**. The process-local run-binding cache is also bounded to 16 entries per document; durable authority remains the bounded document metadata sidecar.

Additional authority: `PRE_EXECUTION_SIDECAR_TAMPER_REJECTION_PASS / BOUNDED_RUN_BINDING_CACHE_PASS`.


## Actual MCP schema projection parity

The TypeScript tool projection is not treated as authoritative merely because codegen emits it. The OAuth lifecycle now compares every P3.46 projected tool against the **actual MCP `tools/list` surface** exposed by FastMCP.

Semantic parity gates:
- exact argument/property set;
- exact required-argument set;
- projected primitive JSON types must be admitted by the actual schema, including nullable Python optionals;
- projected array item primitive types where specified;
- `readOnlyHint`, `destructiveHint`, and `openWorldHint` parity for every projected P3.46 tool.

This turns Python function signatures into a checked host projection of the TypeScript contract instead of an independent, silently drifting schema source.

Required closure authority: `ACTUAL_MCP_SCHEMA_PROJECTION_PARITY_PASS / TOOL_ANNOTATION_PARITY_PASS`.


## Extension identity, capability-version seal and cross-deploy adapter contract pinning

The final pre-closure audit removed three remaining name-based trust assumptions.

- Extension manifests participating in one projection must have unique `extension_id`; duplicate identities fail before inventory merge.
- Every projected tool contract binds the owning capability version and a capability-contract SHA-256 over capability name, version, effect, adapter, determinism and evidence contract.
- The projected tool `contract_sha256` therefore changes when capability semantics/version changes even if the tool name, effect and JSON input schema are unchanged.
- Every pre-admitted host-adapter profile exposes a versioned SHA-256 contract over host ABI, profile identity, guard mode, adapter inventory and revision semantics.
- Run-local binding pins `(profile, generation, profile_contract_sha256)`, and the replay-preserving sidecar seals the same triple.
- Restart recovery validates that fingerprint against the currently admitted profile before any host execution; same-name cross-deploy contract drift fails closed.
- Inspector diagnostics include the fingerprint in within-run configuration-drift detection.
- Docker release smoke carries an explicit profile-contract drift negative control.

Required closure authority:
`UNIQUE_EXTENSION_IDENTITY_PASS / CAPABILITY_VERSION_BOUND_TOOL_CONTRACT_PASS / HOST_ADAPTER_PROFILE_CONTRACT_SEAL_PASS / CROSS_DEPLOY_ADAPTER_CONTRACT_DRIFT_REJECTION_PASS`.


## Combined TypeScript builder module-isolation repair

The production Docker builder compiles the P3.45 runtime CLI and P3.46 platform CLI in one TypeScript program. Dedicated phase CI had compiled them in separate invocations, so their script-global declarations could coexist there while colliding in the combined production image build.

Repair:
- both CLI entrypoints are explicit TypeScript modules via `export {}`;
- no runtime contract or CLI command semantics are changed;
- the production builder can compile both generations in one program without global `process`, `fs` or helper-function collisions.

Required closure authority: `COMBINED_TYPESCRIPT_BUILDER_MODULE_ISOLATION_PASS / PRODUCTION_IMAGE_COMPILE_PARITY_PASS`.

## Replay-sealed sidecar bijection and manifest-local identity hardening

The pre-closure adversarial audit found two residual fail-open seams that were not covered by the earlier provenance-seal rule.

First, a correctly re-hashed P3.46 host-receipt sidecar row could name a node that had no corresponding sealed P3.45 runtime output. A provenance SHA-256 proves internal row integrity, but it does not prove that the row corresponds to an execution admitted by the authoritative replay state. Resume recovery therefore now requires every persisted sidecar row used for adapter re-pinning to have an actual replay-sealed runtime output and binds both `output_sha256` and `receipt_sha256` to that output. Rehashed orphan rows and rehashed output substitutions fail before the next host adapter executes.

Second, the replay-aware inspector previously traversed only the compiled topological order, which meant an extra sidecar key outside the authoritative node set could be invisible to diagnostics. The inspector now reports `HOST_RECEIPT_UNKNOWN_NODE`, missing runtime outputs, invalid sealed runtime hashes, and output/receipt divergence as explicit ERROR diagnostics. An orphan sidecar therefore makes the inspector result fail closed rather than disappearing from the developer view.

The same audit found one manifest-local identity gap in the TypeScript extension validator: duplicate capability names were guaranteed to fail later during merged inventory construction, but a standalone `validateExtensionManifest` call could accept them. Manifest validation now rejects duplicate capability names immediately, so validation and projection share the same uniqueness boundary.

Dedicated P3.46 CI now owns the P3.45↔P3.46 replay-sidecar seam directly. Its Python bridge job builds the P3.45 TypeScript runtime and Rust replay verifier alongside the P3.46 kernel/guard and executes `test_p345_mcp.py`, `test_p346_platform_bridge.py`, and `test_p346_mcp.py` under the same gate.

Required closure authority:
`REPLAY_SEALED_SIDECAR_BIJECTION_PASS / ORPHAN_HOST_RECEIPT_REJECTION_PASS / OUTPUT_AND_RECEIPT_HASH_BINDING_PASS / INSPECTOR_ORPHAN_SIDECAR_DIAGNOSTIC_PASS / UNIQUE_EXTENSION_CAPABILITY_NAME_PASS / DEDICATED_REPLAY_SIDECAR_CI_OWNERSHIP_PASS`.

These labels are closure requirements until the corresponding exact-head GitHub Actions and lifecycle/production gates are observed successful; source presence alone is not treated as execution evidence.

