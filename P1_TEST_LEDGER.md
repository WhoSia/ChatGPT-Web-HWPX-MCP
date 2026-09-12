# ChatGPT Web HWPX MCP — P1 Test Ledger

Date: 2026-09-13
Phase: **P1 — Document-ID/Object-Store Handoff, Minimal Valid HWPX Materialization & Downloadable Artifact Return**
Canonical branch: `main`

## Scope

P1 establishes the first document-custody layer after P0 proved native ChatGPT Web read/write execution.

```text
ChatGPT Web / MCP client
→ create_document
→ opaque document_id
→ bounded ephemeral object store
→ structural HWPX validation
→ inspect_document
→ export_document
→ short-lived signed artifact URL
→ delete_document
```

Existing-document upload/ingest is intentionally **not** authorized in P1.

## Implementation receipts

- Server version: `0.2.0-p1`
- HWPX materializer: `python-hwpx >= 6.4.0, < 7`
- Storage backend: bounded ephemeral filesystem object store under `/tmp` by default
- Default document retention: 1800 seconds
- Opaque document IDs only; server filesystem paths are not returned to clients
- `P1_ACCESS_TOKEN`: generated server-side by Render Blueprint; value is not committed
- `P1_DOWNLOAD_SECRET`: generated server-side by Render Blueprint; value is not committed
- Export URLs: HMAC-SHA256 signed, short-lived bearer links
- Download responses: `Cache-Control: private, no-store`

## Structural HWPX validation

Generated packages are independently checked as ZIP/XML containers. The validator requires:

```text
mimetype
version.xml
META-INF/container.xml
Contents/content.hpf
Contents/header.xml
Contents/section0.xml
```

Additional checks:

- `mimetype` is the first ZIP entry
- `mimetype` uses `ZIP_STORED`
- exact MIME payload is `application/hwp+zip`
- required XML parts parse successfully
- generated XML entries are bounded in size
- SHA-256 and final byte size are recorded

## CI receipts

### T1 — Local/unit HWPX package validation

**PASS**

Latest verified workflow:

```text
Workflow: P1 HWPX lifecycle CI
Run: 34701098865
Commit: 0e2be202b7d239c75348ed72b217148b9a3be04a
Conclusion: success
```

The workflow successfully completed dependency installation, Python compilation, HWPX unit tests, local MCP startup, and the document lifecycle smoke test.

### T2 — Local MCP document lifecycle

**PASS**

The CI lifecycle exercises the guarded MCP path:

```text
create_document
→ inspect_document
→ export_document
→ delete_document
```

using CI-only ephemeral credentials.

### T3 — Render P1 deployment health

**PASS**

Canonical deployed endpoint remains:

```text
https://chatgpt-web-hwpx-mcp-p0.onrender.com
```

The historical `-p0` slug is intentionally retained during P1 to avoid breaking the already-registered ChatGPT custom-MCP URL.

Remote verification waits for `/health` to report `phase=P1`.

### T4 — Remote MCP handshake, discovery, and read probe

**PASS**

Latest verified workflow:

```text
Workflow: P1 Render remote MCP verification
Run: 34701098820
Commit: 0e2be202b7d239c75348ed72b217148b9a3be04a
Conclusion: success
```

The remote workflow confirms P1 health, MCP transport, P1 tool discovery, and the read probe. It deliberately does **not** receive P1 document-write secrets.

### T5 — Native ChatGPT P1 document creation

**PENDING / AUTH BOUNDARY**

P0 already proved native ChatGPT Web write execution. P1 document-mutating tools now require `P1_ACCESS_TOKEN`, but that token is a prototype server-side guard rather than proper MCP authentication. The secret must not be pasted into ordinary chat merely to force a green test.

Therefore native ChatGPT execution of:

```text
create_document
→ inspect_document
→ export_document
→ artifact download
→ delete_document
```

is not yet certified. The next authorization step should replace secret-as-tool-argument with a proper authenticated MCP boundary or another non-secret-leaking test mechanism.

### T6 — Existing HWPX ingest

**INTENTIONAL HOLD**

P1 does not accept arbitrary existing HWPX uploads. Personal/confidential document custody remains unauthorized until authentication, per-user isolation, archive/XML safety limits, and stronger lifecycle controls exist.

## Current verdict

```text
P1-SERVER-IMPLEMENTATION = PASS
P1-MINIMAL-HWPX-MATERIALIZATION = PASS
P1-STRUCTURAL-VALIDATION = PASS
P1-DOCUMENT-ID-CUSTODY = PASS
P1-LOCAL-LIFECYCLE = PASS
P1-RENDER-DEPLOYMENT = PASS
P1-REMOTE-READ-DISCOVERY = PASS
P1-SIGNED-EXPORT-IMPLEMENTATION = PASS_LOCAL_CI
P1-CHATGPT-NATIVE-DOCUMENT-LIFECYCLE = PENDING_AUTH_BOUNDARY
P1-EXISTING-DOCUMENT-INGEST = HOLD
P1-PRODUCTION-AUTH = NOT_YET
```

## Adjudication

P1 has earned promotion from a transport prototype to a real HWPX materialization/custody prototype: it can create a structurally validated HWPX, bind it to an opaque `document_id`, inspect it, issue a bounded signed export capability, and delete it. Both the local lifecycle CI and the deployed P1 read/discovery court pass.

P1 is **not yet closed** because the current access-token tool argument is only a prototype guard. The next world-contact question is no longer whether HWPX generation works; it is whether ChatGPT Web can exercise the complete document lifecycle without exposing a reusable secret and whether the returned signed artifact is usable as the intended downloadable handoff.

## Next decision

Proceed to an authentication/handoff substage before enabling existing-document ingest:

**ChatGPT Web HWPX MCP P1.1 — Authenticated Native Document Lifecycle, Secret-Free Tool Invocation, Signed Artifact Download Receipt & Custody-Boundary Closure**
