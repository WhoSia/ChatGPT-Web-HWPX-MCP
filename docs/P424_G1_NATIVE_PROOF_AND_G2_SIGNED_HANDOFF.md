# P4.24 — Genuine Hancom G1 evidence and signed PDF G2 boundary

Status: **G1 local Windows conversion passed for one authorized document; G2
admission code implemented but not yet independently test-executed or connected
to production storage. Not released.**

## Independently observed G1 evidence (2026-11-06)

The owner ran the P4.24 local WSL2 → Windows PowerShell 5.1 → installed
Hancom Hangul `HWPFrame.HwpObject` workflow using a 12-page authorized
equation-heavy HWPX. Native COM PDF export succeeded after the previous
lock-on-source-hash regression was fixed.

| Observable | Value |
|---|---|
| Hancom product version | 13.0.0.3622 |
| Hancom EXE SHA-256 | 91541f8c16e592516d0265c795b565a14a2cacef0b64f616b0626f54f3d3ece2 |
| Original HWPX SHA-256 | c0f87bd29bbe7261390883d17a4c74f5e9f8d03a240e41f2cc946d63fd914509 |
| Native PDF bytes | 55,235 |
| Native PDF SHA-256 | 2ed549f08cdf78d0fdf2e65280efb3a8615d6ae92bd76c9cb4b13badb563c490 |
| Page geometry | 12 pages, each 595 × 841 pt (near A4) |
| First page | Intentionally blank in source and output |
| Local acceptance | native_pdf_created=true; visual_acceptance=REQUIRES_HUMAN_PAGE_REVIEW |
| Owner's subsequent observation | PDF looks visually identical to original HWPX |
| Independent every-equation audit | Not completed |
| Remote encrypted delivery | Not implemented by this local acceptance |

The user-supplied 55,235-byte PDF was independently parsed and SHA-256
verified against the output receipt. It stays private; never commit its
bytes or full contents to this public repository. Only these aggregate
metadata are reproducible here. The owner report is *not* a signed P4.14
human adjudication.

## Failure genealogy

The first run emitted only a failed receipt, at stage `verify-pdf`, because
Hancom still owned an exclusive file handle when post-render
`Get-FileHash` attempted to read the HWPX. A console-codepage mismatch
in the WSL Python subprocess had also obscured that Windows error. Fixes
are in the development branch (raw PowerShell output bytes; owned COM
release before rehash). A subsequent local run returned a real PDF and
passed source/output digest verification. The failed first receipt must
remain in the owner's local evidence archive.

## G2 authority graph

1. **Authentication:** Derive owner subject from existing OAuth middleware,
   never from an MCP argument.
2. **Exact revision:** Fetch encrypted document revision and SHA-256 from
   the existing DurableDocumentStore; pin or lease as appropriate.
3. **Signed P4.14 job:** A specific source manifest, exact head,
   document binding (including owner subject) and one-time nonce.
   Only a registered, active Ed25519 key is accepted.
4. **Windows execution:** P4.14 worker produces the native PDF and signs
   a receipt. Private source bytes never enter a public repo.
5. **Admission:** `hwpx_mcp/custody/p424_signed_pdf_handoff.py`
   calls the existing `verify_signed_receipt` and compares the actual PDF
   bytes, sha256, byte length, source digest, fixture identity, job HEAD,
   owner, revision, captured status and human verdict. It refuses
   multi-document capture batches for single-document delivery.
6. **Replay protection [NOT CONNECTED]:** Call P4.14 durable
   `P414EvidenceStore.record_attempt` or equivalent replay/nonce
   admission atomically and reject anything but newly accepted or
   expressly idempotent authorized retries.
7. **Encrypted PDF custody [NOT CONNECTED]:** Add a separate encrypted
   PDF artifact keyed by authenticated owner, document ID, exact revision,
   SHA-256 and accepted signed evidence ID. Preserve immutable bytes.
8. **Download [NOT CONNECTED]:** Issue revocable, short-lived,
   owner-scoped URLs and verify access on every retrieval. The signed
   agent receipt must not become an access token.
9. **Release validation [NOT CONNECTED]:** Verify a real remote capture
   and downloaded PDF's digest; complete full-page human visual inspection.

No local evidence can independently certify steps 6–9.

## P4.24 source locations

- `hwpx_mcp/custody/p423_hancom_pdf.py`: direct Windows worker; no
  console decoding assumption; verifies original and PDF digest plus bytes.
- `tests/test_p424_native_pdf_worker_custody.py`: CP949, modified source,
  output-size mismatch with mocked PowerShell.
- `hwpx_mcp/custody/p424_signed_pdf_handoff.py`: pure, fail-closed
  P4.14-receipt/actual-bytes admission check (does not store/deliver).
- `tests/test_p424_signed_pdf_handoff.py`: synthetic Ed25519 signing and
  owner/bytes/head/visual rejection cases.

## Acceptance and nonclaims

- No current development-branch CI pass is inferred until exact-head
  runs are fetched and evaluated.
- One local Hancom successful PDF is not production signed-worker
  orchestration or general renderer compatibility.
- Code-only tests are not real Hwp.exe proof.
- The G2 admission checker deliberately always reports
  `production_delivery_authorized=false` to prevent accidental
  promotion ahead of durable replay, encrypted storage and download.
