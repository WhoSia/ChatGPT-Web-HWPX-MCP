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

## 2026-11-06 follow-up — encrypted PDF custody primitive (still not deployed)

`hwpx_mcp/storage/p424_pdf_store.py` adds a separate Postgres-backed AES-GCM
ciphertext store. The encryption key is domain-separated from HWPX revision
encryption and derived from the server-side secret, never from the PDF receipt.
The AEAD associated data binds accepted signed evidence ID, document ID,
revision, authenticated owner subject, source HWPX SHA-256, and PDF SHA-256.
The table forbids overwriting an existing evidence ID with a different
artifact. Its `put_verified` method requires the previous G2 admission
result and checks for a matching **durably accepted P4.14 evidence record**
through `P414EvidenceStore.accepted_receipt_by_id`. Its
`load_owned` method checks the live `DurableDocumentStore.load_revision`
owner and digest before decrypting and rehashing the PDF.

Companion `tests/test_p424_pdf_store_contract.py` checks the cryptographic
AAD and rejection contract, but Postgres transaction and schema integration
have not yet been exercised in an actual database, and the store has not
been wired into the deployed MCP. No URL endpoint exists and no download
is marked delivered. The source revision's retention/pinning lifecycle
must be designed before production activation.

The owner's WSL tests of the *preceding* P4.24 branch HEAD
`da9cca4` passed 31 P4.24 + 7 P4.23 tests. These tests predate the
new P4.24 storage commits and are not evidence that the storage integration
has passed. CI on the newer exact HEAD is not verified.

## 2026-11-06 next cycle — revision deletion and authenticated PDF links

The owner executed the previous `66dfe16` WSL regression suites: 5/5
PDF custody contract tests, and 36/36 P4.24 tests overall, both without
failures. These are *mock and cryptographic unit tests*, not a Postgres
round-trip or server route test.

The storage FK policy was audited and corrected. `ON DELETE RESTRICT`
would have prevented deleting/compacting HWPX source revisions whenever
a native PDF existed. New schema uses `ON DELETE CASCADE`, ensuring the
encrypted PDF is removed when its source revision is removed. A startup
invariant rejects any pre-existing incompatible FK instead of silently
accepting it; an existing database must be explicitly migrated in a
controlled change, not silently rewritten. Distinct signed captures may
produce the same PDF hash for a revision, so the former uniqueness on
(document_id, revision, pdf_sha256) was removed. Evidence ID remains the
immutable record identity.

`tests/test_p424_pdf_store_postgres_integration.py` is an opt-in *real*
Postgres integration test (owner isolation, AES-GCM ciphertext, exact
idempotent replay and source deletion cascade). It uses an ephemeral
schema, but must run only against an explicitly designated disposable
test DB using BOTH `P424_TEST_DATABASE_DISPOSABLE=YES` and
`P424_TEST_DATABASE_URL`; it skips otherwise. No real DB integration
execution is claimed yet.

`hwpx_mcp/delivery/p424_pdf_delivery.py` adds a pure delivery contract
with HMAC-SHA256 over authenticated owner, document ID, revision, source
SHA, evidence ID, PDF SHA and expiry (60–900 seconds bounded by source
retention). Unlike a simple bearer URL, redemption REQUIRES a fresh
OAuth-derived owner subject: a copied URL alone is insufficient. It
re-validates the retained source and decrypts via the owner-scoped PDF
store. `tests/test_p424_pdf_delivery_contract.py` supplies mocked
cross-owner, expiration, tampering and source-retention regressions.

**Important distinction:** There is still no installed P4.24 MCP
download route, remote signed agent job transport or actual production
PDF download. This code must not be marked deployed. To complete G2:
wire an authenticated route and issuance tool, enforce no-store response
headers, exercise a real disposable Postgres integration test, test
key-rotation/revocation and delivery end-to-end, then check exact HEAD CI.

## 2026-11-06 — Feature-gated OAuth PDF route (not deployed)

The P4.24 development branch now registers a PDF link-issuance MCP tool
`issue_p424_native_pdf_download` and HTTP GET path
`/p424/native-pdf/{document_id}` in `server.py`.
`hwpx_mcp/delivery/p424_pdf_http.py` validates a **fresh OAuth bearer
Authorization header** on every request through the existing OAuth provider,
including expected scope, subject and resource/audience. A copied signed URL
*without* an Authorization header returns HTTP 401: this is NOT a normal
browser-click download. A client must support authenticated HTTP retrieval.
Never append access tokens to the PDF URL or include them in logs.

The route is **disabled by default**. Activating it requires an explicit
`P424_NATIVE_PDF_DELIVERY_ENABLED=YES` flag, valid HTTPS public URL,
`P424_PDF_DATABASE_URL` pointing to the *same database* holding source
revision tables, an existing >=32-byte server secret and already accepted
native PDF ciphertext. The first enabled use initializes the PDF store;
subsequent uses reuse the initialized instance. The route does not import
private PDF bytes from Windows, deploy a remote capture worker, or generate
new HWPX/PDF content. It will return 404 for missing/invalid/expired document
bindings without revealing document owner existence.

Security corrections in this development cycle:

- Explicit artifact retrieval now **requires** document ID, exact revision
  and source SHA-256. Owner identity alone was insufficient: the same owner
  could have multiple HWPX documents and previously could mix signed URLs
  with another document's PDF artifact. A read without exact binding is no
  longer allowed by the storage API.
- The PDF route's signed URL binds owner, document, revision, source SHA,
  signed evidence ID, actual PDF digest and short expiry. Every redemption
  retrieves the retained source revision and owner-matched encrypted PDF.
- Invalid opaque document IDs or evidence IDs are rejected; PDF failure
  responses never expose database secrets, filesystem paths or source data.
- The page uses `Cache-Control: private, no-store`,
  `X-Content-Type-Options: nosniff` and a fixed safe download filename.

Tests: `tests/test_p424_pdf_http_adapter.py` (feature flag disabled,
missing/malformed/invalid bearer, missing OAuth scope/wrong audience/owner,
authorized GET, URL tampering); modified PDF store/delivery tests cover
same-owner cross-document confusion. These latest commits have **not** yet
been run on the owner's WSL or in a deployed MCP host. Do not call G2
production complete.

Activation prerequisites before use:
1. Complete and test real signed P4.14 job creation, upload, verification,
   replay gate and `put_verified` ingestion into Postgres.
2. Execute full P4.24 suite, including the opt-in real disposable Postgres
   test; verify no old RESTRICT foreign-key schema remains.
3. Prove OAuth-authenticated GET roundtrip from a real MCP client, including
   missing/expired bearer and cross-user denial. Browser-click support is
   not implied.
4. Validate retention/deletion/key revocation, CI exact HEAD, rollback and
   Render staging; do not change production configuration before these gates.

## 2026-11-06 — P4.24 signed-job ingest coordinator and durable job authority

New server-side primitives (NOT enabled as public ingestion endpoints):

- `hwpx_mcp/custody/p424_job_store.py` persists one server-issued,
  expiring job authority in PostgreSQL. Its issuer checks the authenticated
  owner against the retained source revision and SHA-256, validates the
  one-file P4.14 source manifest including fixture ID, source digest and
  byte count, and stores nonce, job ID, exact HEAD and expiration.
  `load_issued_job` returns only still-`ISSUED`, unexpired jobs.
  Revocation is owner-scoped. Source revision deletion cascades to jobs.
- `hwpx_mcp/custody/p424_signed_pdf_ingest.py` coordinates existing
  `verify_signed_receipt`, `P414EvidenceStore.record_attempt` and
  `P424PdfStore.put_verified`. It loads the job authorization from the
  trusted job store by the signed `job_id`, never from untrusted request
  data. Signed nonce, owner, source digest, source manifest, fixture,
  exact HEAD and document revision must agree before any evidence insert.
  It passes the complete authoritative P4.14 verifier result to
  `record_attempt`. Stored evidence is independently required before
  ciphertext commit.

The evidence and PDF records are two durable transactions, **not an
atomic distributed transaction**. A crash after evidence acceptance but
before PDF storage leaves a recoverable evidence-only record. A repeat
using the *identical* signed receipt and immutable PDF bytes can finish
custody idempotently while the signed job and receipt remain valid.
Do not claim the PDF delivered until the ciphertext has been verified
and an authenticated retrieval actually succeeds.

New tests `test_p424_signed_pdf_ingest.py` and
`test_p424_issued_job_store.py` cover synthetic Ed25519 evidence,
source mutation, wrong user, mismatched job/nonce/manifest, replay
denial, transient PDF-write failure followed by identical receipt
recovery, owner-scoped job issuance and revocation. These tests have
been committed but **not yet executed by the owner** at this exact HEAD.

**Outstanding gates:**
- The server-side source-to-agent job envelope creation, secure Windows
  transport, remote agent upload protocol and server-hosted ingest route
  are NOT implemented in this cycle.
- An independent one-time job authorization record needs a real,
  disposable PostgreSQL integration test and operational retention audit.
- `P424_NATIVE_PDF_DELIVERY_ENABLED` must remain OFF until the signed
  job-to-PDF chain has been demonstrated end to end with owner OAuth.
- Latest-head Python suite, CI, key revocation behavior and actual
  Postgres integration still require execution; no production deploy.

### Disposable PostgreSQL test for job authority

`tests/test_p424_job_store_postgres_integration.py` is an additional
opt-in test requiring the same explicit `P424_TEST_DATABASE_DISPOSABLE=YES`
and `P424_TEST_DATABASE_URL` as the PDF storage integration test. It
creates a random schema, issues a synthetic job, checks exact retrieval,
duplicate rejection, owner-scoped revocation and source deletion cascade.
Absent the explicit opt-in, it **SKIPs**, which is not proof of PostgreSQL
integration. A disposable DB is required; never aim it at production.

### 2026-11-06 final authorization tightening

Issued jobs now bind `agent_id` as well as `job_id`, `nonce`,
`document_id`, exact revision, source SHA-256, canonical single-file
source manifest digest, exact head, owner and short expiry. Ingestion
compares the receipt's signed `agent_id` with the server-authorized
agent, so a different *registered* agent cannot substitute a signature
for a job it was not assigned. This is separate from checking whether
the public key is registered and active.

No production bearer upload or native Windows job transport was exposed.
Until the server schedules a real job, obtains an agent response and
verifies the final PDF bytes over authenticated transport, the G2 lane
remains a prototype. Full integration tests are pending.
