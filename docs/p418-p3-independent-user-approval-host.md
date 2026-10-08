# P4.18-P3 — Independent Human Approval Host Runbook

## Scope

Opt-in, single-owner browser confirmation for one server-staged EDIT_INTENT.
Not a replacement for the legacy OAuth-scoped P4.18 task API. Not a
declaration of native visual fidelity or P3 PRODUCT CLOSED. Disabled by default.

## Required protected environment settings

- P12_STATE_SECRET: existing strong server secret (at least 32 characters).
  Used with domain-separated AES-256-GCM to encrypt the complete review
  snapshot, with random nonce and workflow/owner associated data.
- P418_HOST_REVIEW_PASSPHRASE: independent, human-held secret (24+ characters).
  Never reuse the OAuth passphrase, state secret or signing key.
- P418_HOST_APPROVAL_SIGNING_SECRET: independent, server-only signing key
  (32+ characters). Do not paste into chat, GitHub, logs or HTML.
- PostgreSQL durable document/admission stores must be configured.

Use protected Render secret settings. Never display secret VALUES in status
readbacks. Staging returns a human_review_url only when the approval host is
configured. The URL is a pointer, not a bearer credential.

## End-to-end human flow

1. An OAuth-authenticated MCP client compiles/previews a single document edit.
2. The stage tool verifies live ownership and revision, writes the immutable
   STAGED admission fingerprints, encrypts and durably stores the entire
   normalized draft/preview/source bindings. It aborts admission if encryption
   or durable snapshot storage fails.
3. A human opens the independent HTTPS review URL, enters the dedicated
   passphrase, and reads the exact original document/revision/SHA, complete
   requested actions, referenced documents, preservation rules and review hash.
   Lease tokens are redacted.
4. After reviewing the COMPLETE effects, the human explicitly approves or
   denies, reentering the passphrase. The host verifies request Origin,
   exact review hash, auth-attempt count and immutable STAGED fingerprints.
5. On approval, the host issues a short-lived, scope-bound signature with
   its server-only key and CAS-promotes the PostgreSQL record to APPROVED.
   Only the host obtains an approval key. The browser and MCP agent never do.
6. The trusted native adapter revalidates source ownership/revision/SHA,
   executes a single edit, reads the durable document-store commit receipt
   independently and records COMMITTED. Unknown outcomes are quarantined;
   second POST cannot blindly repeat a mutation.
7. The user obtains the committed document with the existing OAuth-authenticated
   deliver_document tool and the exact output revision.

The approval URL does not carry a session bearer token. This single-user
host authenticates the fixed oauth_provider.SUBJECT via a separate password;
multi-tenant use needs redesigned identity and security review.

## Controls

- Five wrong password submissions lock the staged workflow.
- Browser POSTs require same-origin Origin, URL-encoded bounded bodies with
  no duplicates or unexpected fields; document text is HTML-escaped.
- No scripts or framing are permitted in the response CSP.
- A caller-created hash is NOT consent or authorization.
- Stale revisions, unknown custody, ciphertext corruption, wrong owners,
  mismatched review hashes or unverified commit receipts fail closed.
- Real Hancom display verification is independent of ZIP structure validation.

## Remaining launch gates

Exact-head kernel, PostgreSQL, Docker, Windows and lifecycle success;
public staging host confirmation smoke with a real document, one-click denial,
double-click/parallel submits, stale source conflict, crash-after-commit
reconciliation, exact native bytes and revision handoff, latency p50/p95,
production boundary observation, rollback drill, and independent review of
host secret custody. Keep P3 RELEASE_HOLD until all evidence is recorded.

Rollback: unset either P418_HOST_REVIEW_PASSPHRASE or
P418_HOST_APPROVAL_SIGNING_SECRET to disable the new browser route with HTTP
503 without changing legacy OAuth MCP features. This cannot undo already
committed mutations; use explicitly authorized revision restoration.
