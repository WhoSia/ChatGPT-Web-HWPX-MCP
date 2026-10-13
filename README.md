# ChatGPT Web HWPX MCP

**Create, understand, edit, and deliver Korean Hangul documents from ChatGPT.**

[Product authority](PRODUCT_AUTHORITY.md) · [Architecture](docs/ARCHITECTURE.md) · [Feature catalog](docs/FEATURE_CATALOG.md) · [Tests](tests/) · [CI](.github/workflows/)

A remote, authenticated [Model Context Protocol](https://modelcontextprotocol.io/) server for native `.hwpx` documents. It combines structured document authoring, format-aware inspection, revision-safe editing, explicit human approval for protected changes, and secure HWPX delivery.

> **Release boundary:** P4.19 domain refactor merged via [PR #13](https://github.com/WhoSia/ChatGPT-Web-HWPX-MCP/pull/13); P4.20 runtime repairs [PR #14](https://github.com/WhoSia/ChatGPT-Web-HWPX-MCP/pull/14) **merged 2026-10-09 23:25 KST** (main `1b28199b...`), and P4.20 packaging/integration [PR #15](https://github.com/WhoSia/ChatGPT-Web-HWPX-MCP/pull/15) **merged 2026-10-12 15:11 KST** (`950bff8d3ed16f1d6eda20e190b2b32cd8280733`). Current [PR #16 · P4.21](https://github.com/WhoSia/ChatGPT-Web-HWPX-MCP/pull/16) remains **OPEN/DRAFT and unmerged**, at head `d47984e1e7d639873801dbe27a9f508790666463` at 2026-10-13 audit. `main` observed at `065922057645abc9ae2b27c9c18a5cca2bce84a2` before this docs-only correction. The last independently reported Render observation (2026-10-09) served `0.43.0-p4.18` (`30d536d…`); **current Render deployed commit / production feature parity UNVERIFIED** because workspace selection was not available in this audit. No published GitHub Release was returned. P4.18-P3 independent consumer preservation/delivery remains HOLD; PR merge and CI are not native Hancom quality, public API end-to-end, or production deployment certificates.

## What you can do

| Goal | Current product surface | Important boundary |
| --- | --- | --- |
| **Create a document** | Natural-language plans, `generate_document`, `run_p418_document_task` | Validate generated HWPX before delivery |
| **Understand an HWPX** | Inspect, semantic graph, document map, document workspace overview | Structural inference is not proof of Hancom rendering |
| **Prepare a change** | `prepare_document_title_change` (merged P4.19 code; production admission pending) | One tool call compiles, previews and **stages** a title edit; never executes it |
| **Approve an edit** | Separate authenticated browser review (P4.18-P3) | Only the human approves; ChatGPT tool payload cannot self-authorize |
| **Continue / deliver** | Revision history, durable commit receipts, revision-bound export | Download/read-back is verified separately; 429 or expiry must not trigger mutation replay |

### Typical workflow

1. Ask ChatGPT to create a report or inspect an existing HWPX.
2. Review its structure, requested scope and suggested changes.
3. For an approved editing capability, open the **independent browser review** when a mutation is staged.
4. After explicit approval, inspect the new revision and request its download.
5. Verify downloaded bytes and openability before relying on the final document.

The newer `get_document_workspace` view consolidates revision, history, expiry and receipt information. No one has to pass three intermediate JSON payloads merely to understand document status. These P4.19 conveniences are present on `main`; production availability and actual consumer behavior require independent live deployment verification.

## Start the server

**Requirements:** Python 3.12 recommended, a supported PostgreSQL database, and valid server-side authentication/encryption configuration. The public hosted endpoint is `https://chatgpt-web-hwpx-mcp-p0.onrender.com/mcp`; its Render hostname is historical and does not guarantee the latest `main` code is deployed.

```bash
python -m pip install -r requirements.txt
python server_p2.py
```

The local command requires the deployment configuration documented by the runtime; do **not** hardcode OAuth passwords, signing keys, state encryption secrets or PostgreSQL credentials in code, tests, tool arguments or GitHub Actions logs. To connect ChatGPT, use the MCP endpoint with the configured OAuth flow; the browser-based human edit approval uses a separate authenticated host boundary.

## Repository architecture

```text
ChatGPT-Web-HWPX-MCP/
├── server.py, server_p2.py           # Protocol / production entrypoints
├── auth_store.py, document_store.py # Core authenticated custody
├── hwpx_mcp/
│   ├── orchestration/               # Agent workflows, preview, staging
│   ├── interfaces/                  # MCP tool registration facades
│   ├── corpus/                      # Reusable corpus & style intelligence
│   ├── document/                    # Native document parsing primitives
│   ├── custody/                     # Capture, replay and evidence custody
│   └── probes/                      # Bounded external world-contact test CLIs
├── tests/                            # Regression and boundary tests
├── scripts/                          # Operational / compatibility tools
├── benchmarks/, corpus/, fixtures/   # Evaluation and materialization inputs
├── docs/                             # Architecture and extended catalog
└── .github/workflows/                # Human-authored CI; no bot commits
```

P4.19 migration is **merged**: the Python root now contains **89 modules** (previously 263). Legacy feature names remain intentionally supported. Keep moving modules only when it improves domain ownership and runtime operability; do not combine unrelated engines just to optimize a file-count metric. See [Architecture and migration policy](docs/ARCHITECTURE.md).

## Development and verification

```bash
python -m pytest -q
python scripts/p419_layout_audit.py
python -m py_compile server.py server_p2.py
```

The layout audit checks test location, module relocation, import backlinks and workflow test paths. Product/kernel, PostgreSQL, exact-head Docker, Windows, full lifecycle and live Render checks are separate gates. Linux tests do **not** establish Hancom-native visual fidelity; renderer evidence requires controlled Windows/Hancom capture.

- **Source of truth:** [PRODUCT_AUTHORITY.md](PRODUCT_AUTHORITY.md), with phase evidence archived in the project Drive.
- **Full feature inventory:** [docs/FEATURE_CATALOG.md](docs/FEATURE_CATALOG.md).
- **Branch policy:** small bounded fixes go directly to `main` after appropriate validation; large cross-layer refactors use a short-lived branch and PR, then can be deleted after preserving required history. P4.20 PR #14 and PR #15 are already merged; complete P4.21 PR #16 only after source/current-branch, integration, independent native quality, rollback and live-prod gates. Do not mistake the unmerged Draft branch for production. Never rewrite unrelated history or delete protected/historical refs implicitly.
- **Commit policy:** GitHub Actions **tests and builds only**; commits are authored by the human-connected `WhoSia` GitHub identity, never `github-actions[bot]`.
- **Release policy:** merge, native certification and production deployment are separate explicit decisions. No automatic promotion of HOLD evidence.

## Current priorities

Product quality means users can request a useful document, make understandable changes and get an actually openable `.hwpx` file. P4.20 PR #14/#15 are merged as source revisions; P4.21 PR #16 is active Draft. Priorities are current-main/PR reconciliation, native Hancom visual evidence, owner-approved formatting and revision-safe live API editing, exact deployed SHA and real consumer acquisition. Preserve earlier COM `0x80070005` failures and native manual-GUI results as separate evidence: test-only success does not certify the production service. Independent Hancom native fidelity remains an explicit gate; byte counts are diagnostic signals, not the product goal.
