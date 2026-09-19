# P3.2-R2 Test Ledger

## Phase

**ChatGPT Web HWPX MCP P3.2-R2 — Production Authenticated-MCP Edge Transport Isolation, Bearer `/mcp` Reachability, Proxy/Protocol Compatibility Repair & Native Pin→Compact→Verify Final Closure**

## Verdict

`IMPLEMENTATION_PASS / PRODUCTION_OAUTH_PASS / MCP_SURFACE_PASS_LOCAL / RENDER_FREE_INSTANCE_RECYCLE_HOLD / FULL_CLOSURE_NOT_EARNED`

## Canonical production alignment

- Canonical main head: `f8d1091e4fe3f3cf95deb68e4ab9d30dbe6b983f`
- Explicit Render deploy: `dep-dan566h42hec73d8q64g`
- Deploy status: `live`
- Production was therefore aligned with the R2 diagnostics before the final replays.

## R2 isolation sequence

R2 progressively removed the following candidate causes:

1. **Bearer lookup failure** — rejected.
   - A protected out-of-MCP bearer lookup probe was added and exercised.
2. **Authorization-header-only failure** — rejected.
   - Auth/no-auth/bogus-bearer paths were separated.
3. **MCP protocol-header incompatibility** — not sufficient.
   - Modern pinned, legacy, and raw-wire variants were tested.
4. **HTTP/2 / connection reuse** — not sufficient.
   - The production probe forces HTTP/1.1 and `Connection: close`.
5. **Render deploy drift** — removed as a confounder.
   - Production was explicitly redeployed to the canonical R2 head before rerun-only tests.
6. **OAuth authority** — confirmed.
   - DCR, authorization, approval, and token issuance repeatedly complete successfully.
7. **CPU / memory exhaustion** — rejected.
   - Around the restart windows CPU remained approximately 0.004–0.006 CPU and memory approximately 72–76 MB.

## Stable-edge replay evidence

World-contact run: `35432517773`

The probe performs:

`DCR → authorize → approve → token → stable-edge gate → bearer probe → MCP ping → tools/list → create/edit → pin → lease-block → compact → verify → cleanup`

Multiple rerun attempts were made **without new pushes** to avoid deployment churn.

Observed repeatedly:

- OAuth: `DCR+PKCE+token PASS`
- Immediately after token issuance, the GitHub runner observed repeated public `/health` HTTP 502 responses.
- At the same timestamps, Render application logs showed the running instance returning HTTP 200 to its own health checks.
- The MCP application therefore was not itself hung or returning those 502 responses.

## Instance recycle evidence

The same Render instance id, `srv-daiimp8ae00c73em8tjg-55cwj`, was observed undergoing repeated graceful process replacement:

- `09:19:34Z` — `Shutting down`
- `09:19:37Z` — process finished
- `09:19:55Z` — process started
- `09:21:34Z` — `Shutting down`
- `09:21:37Z` — process finished
- `09:21:56Z` — process started
- `09:24:38Z` — `Shutting down`
- `09:24:55Z` — process started

No new deploy record accompanied these repeated process replacements.

The shutdowns were graceful rather than OOM/crash signatures, and application health checks were returning 200 immediately before the shutdown windows.

## External-platform interpretation

Render's public documentation states that Free web services may be restarted by Render at any time, while ordinary idle spin-down occurs only after 15 minutes without inbound traffic. The observed service was receiving active traffic, so ordinary idle spin-down does not explain the measured pattern.

Render's public status page reported Singapore and Free Web Services operational with no Sep 19 incident. Therefore this is treated as a **service/instance-specific Free-tier lifecycle instability**, not a documented region-wide incident.

## Earned authority

Confirmed:

- P3.2 durable lineage implementation
- revision CAS and lease semantics
- pin/compaction/restore-reachability logic
- tamper-evident audit chain
- local/native confirmatory lifecycle
- production Render deployment of R2 diagnostics
- OAuth DCR + PKCE + approval + token issuance
- bearer lookup path outside MCP transport
- HTTP/1.1 / connection-close transport variant
- repeated evidence that the application remains healthy while the public runner receives 502s

Not yet earned:

- uninterrupted authenticated production `tools/list`
- production `pin → compact → verify`
- P3.2 final full closure

## Safety/authority boundary

No paid-plan upgrade, region migration, second paid service, or billing-affecting action was performed without explicit user authorization.

## Next boundary

**ChatGPT Web HWPX MCP P3.2-R3 — Render Free-Instance Recycle Adjudication, Restart-Aware World-Contact Harness, Support-Grade Evidence Packet & Paid-vs-Free Closure Boundary**

The preferred next move is to keep the application contract frozen and treat the remaining problem as infrastructure reliability rather than continue modifying P3.2 semantics.
