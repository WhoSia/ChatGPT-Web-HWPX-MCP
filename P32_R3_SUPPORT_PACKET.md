# P3.2-R3 Support Evidence Packet

## Phase

**ChatGPT Web HWPX MCP P3.2-R3 — Render Free-Instance Recycle Adjudication, Restart-Aware World-Contact Harness, Support-Grade Evidence Packet & Paid-vs-Free Closure Boundary**

## Executive finding

The surviving production failure is localized outside the HWPX application and outside OAuth semantics.

The Render Free web service repeatedly presents a public-edge 502 window while the application instance itself continues to answer Render-internal health checks with HTTP 200, followed by graceful process replacement.

## Canonical deployment

- Service: `chatgpt-web-hwpx-mcp-p0`
- Region: Singapore
- Plan: Free
- Explicit R3/P3.3 deploy: `dep-dan5eq8ae00c73diq5b0`
- Deployed commit: `dfb34c09d5aed73b55fffbcd006a21dbf7efa9cb`
- Deploy status: `live`

## Restart-aware harness

The production harness now:

1. restarts the complete DCR + PKCE authorization flow after transient 502/503/504 failures,
2. waits for a bounded public-edge stability window before mutation,
3. uses HTTP/1.1 without the prior forced `Connection: close` diagnostic confounder,
4. uses replay-safe `create_document(request_id=...)`,
5. retries safe MCP reads/lists across transient transport failures,
6. preserves CAS-based edit authority,
7. keeps cleanup retryable.

World-contact workflow:
- `.github/workflows/p32-world-contact.yml`
- probe: `p32_public_world_contact.py`

## Production attempt receipt

Workflow run: `35435187085`

Observed by GitHub Actions:

- setup reduced to the raw probe dependency only,
- OAuth flow restarted after transient failure,
- all 8 fresh OAuth flow attempts encountered public HTTP 502 at `/register`,
- no document mutation was started,
- the harness failed closed after exhausting its bounded restart window.

## Same-time Render evidence

During the same public failure interval, Render application logs for instance
`srv-daiimp8ae00c73em8tjg-6d2xr` showed repeated successful internal health checks:

- 09:37:12Z — `GET /health` 200
- 09:37:15Z — `GET /health` 200
- 09:37:19Z — `GET /health` 200
- 09:37:22Z — `GET /health` 200
- 09:37:25Z — `GET /health` 200
- 09:37:28Z — `GET /health` 200
- 09:37:31Z — `GET /health` 200
- 09:37:34Z — `GET /health` 200
- 09:37:37Z — `GET /health` 200 immediately before graceful shutdown

Then:

- 09:37:37Z — `Shutting down`

The GitHub runner's 502s therefore were not application-generated 502 responses and did not correspond to an application health failure.

Earlier R2 observations also recorded repeated graceful process replacement windows without matching deploy records.

## Resource evidence

Around prior recycle windows:

- CPU usage remained approximately 0.004–0.006 CPU.
- Memory usage remained approximately 72–76 MB.
- No OOM or crash signature was observed.
- Shutdowns were graceful.

## Adjudication

Rejected as primary cause:

- P3.2 lineage semantics
- OAuth passphrase authority
- DCR / PKCE implementation
- bearer lookup logic
- MCP protocol selection alone
- HTTP/2 alone
- forced connection reuse alone
- CPU exhaustion
- memory exhaustion
- ordinary application health-check failure

Surviving cause family:

**Render Free-service public routing / instance lifecycle instability.**

This packet does not claim a Render platform defect beyond the observed service-specific evidence.

## Paid-vs-Free boundary

No billing-affecting action was taken.

A paid-plan upgrade, paid second service, or paid region migration may be a reasonable experimental contrast, but it is outside automatic authority and requires explicit user approval.

## Scientific authority

R3 earns:

`FREE-TIER_INFRASTRUCTURE_LOCALIZATION / RESTART-AWARE_HARNESS_PASS / SUPPORT_PACKET_SEALED`

R3 does not earn:

`UNINTERRUPTED_PRODUCTION_NATIVE_MCP_FULL_CLOSURE`
