# ChatGPT Web HWPX MCP — P0 Test Ledger

Date: 2026-09-12
Deployment URL: https://chatgpt-web-hwpx-mcp-p0.onrender.com

## Environment

- Hosting: Render Web Service, Singapore region
- Render service: `chatgpt-web-hwpx-mcp-p0`
- MCP URL: https://chatgpt-web-hwpx-mcp-p0.onrender.com/mcp
- Health URL: https://chatgpt-web-hwpx-mcp-p0.onrender.com/health
- Authentication selected in ChatGPT: **No authentication**
- ChatGPT custom-app registration: **PASS**
- ChatGPT app recognition: **PASS**
- ChatGPT app-specific permission: **Allow all actions**
- Global app permission: **Allow low-risk actions**
- `P0_WRITE_NONCE`: enabled; temporary test nonce retired after certification and rotated to a fresh secret
- Canonical Git branch: `main` only

## Infrastructure receipts

- Local GitHub Actions MCP smoke test: **PASS**
- Render external `/health`: **PASS**
  - Receipt: `{"status":"ok","project":"ChatGPT Web HWPX MCP","version":"0.1.1-p0"}`
- Remote MCP protocol handshake: **PASS**
  - Negotiated protocol: `2026-07-28`
  - Server name: `ChatGPT Web HWPX MCP`
- Remote tool discovery: **PASS**
  - `probe_read`
  - `probe_write`
  - `probe_capabilities`
- Remote `probe_read` transport execution: **PASS**

## ChatGPT Web boundary tests

| Test | Result | Evidence / error |
|---|---|---|
| T0 `/health` | ☑ PASS | External GitHub Runner received version `0.1.1-p0` from Render |
| T1 ChatGPT custom-app registration | ☑ PASS | ChatGPT recognizes `ChatGPT Web HWPX MCP` as a registered app |
| T1b ChatGPT app permission inspection | ☑ PASS | App-specific permission = `Allow all actions`; global = `Allow low-risk actions` |
| T2 same-chat app selection / @mention accepted | ☑ PASS | Original chat accepted app selection; tool refresh there was inconclusive |
| T2c fresh-chat native `probe_read` execution | ☑ PASS | Fresh chat + `@ChatGPT Web HWPX MCP` successfully invoked `probe_read` |
| T2d fresh-chat read receipt | ☑ PASS | `ok=true`, project=`ChatGPT Web HWPX MCP`, version=`0.1.1-p0`, probe=`read`, echo=`ChatGPT Web P0-R3 fresh-chat read test` |
| T3 `probe_write` exposed in fresh-chat selected-message tool surface | ☑ PASS | ChatGPT exposed and invoked `probe_write` natively |
| T4 ChatGPT `probe_write` reaches server | ☑ PASS | Initial write attempts reached the MCP server; Render logs localized failure to `ValueError: Invalid P0 write nonce` |
| T4b authorized write mutation completes | ☑ PASS | Authorized native call returned `ok=true`, version=`0.1.1-p0`, and created remote artifact `p0-write-20260912T144608Z-73c110d5.txt` |
| T4c artifact materialization | ☑ PASS | Remote artifact size = `49 bytes`; artifact exists on the remote MCP host |
| T4d post-test secret rotation | ☑ PASS | Temporary certification nonce retired; Render `P0_WRITE_NONCE` rotated to a fresh secret and redeploy initiated |

## Final P0 verdict

```text
REMOTE-RUNTIME = PASS
REMOTE-MCP-TRANSPORT = PASS
REMOTE-TOOL-DISCOVERY = PASS
CHATGPT-REGISTRATION = PASS
CHATGPT-APP-PERMISSION = ALLOW_ALL_ACTIONS
CHATGPT-FRESH-CHAT-NATIVE-TOOL-INJECTION = PASS
CHATGPT-READ-ACTION = PASS
CHATGPT-WRITE-EXPOSURE = PASS
CHATGPT-WRITE-SERVER-REACHABILITY = PASS
CHATGPT-WRITE-MUTATION = PASS
REMOTE-ARTIFACT-CREATION = PASS
PRODUCT-WRITE-BLOCK = NO EVIDENCE
P0 = CLOSED / PASS
```

## P0-R3-R4 closure adjudication

P0's intended question is now answered end to end. ChatGPT Web can register the custom remote MCP, discover its tools, invoke a side-effect-free read action, expose a write action, deliver an authorized write invocation to the Render-hosted MCP server, and cause an actual remote mutation. The successful authorized receipt created `p0-write-20260912T144608Z-73c110d5.txt` with a measured size of 49 bytes.

The earlier write failures were not product-level action blocks, filesystem failures, or serialization failures. Render logs localized them to the application-level nonce guard (`ValueError: Invalid P0 write nonce`). After binding the intended test nonce into the live Render runtime, the same native write path succeeded.

The temporary certification nonce has been retired and replaced with a fresh secret. The replacement secret is intentionally not recorded in this repository or ledger.

## P1 authorization boundary

P0 does **not** authorize personal HWPX custody under the current no-auth prototype. P1 may now begin implementation of:

1. `document_id`-based custody rather than raw filesystem paths,
2. minimal valid HWPX materialization,
3. object-store / short-lived artifact handoff suitable for ChatGPT,
4. structural validation before export,
5. proper authentication and per-user/session isolation before handling real personal documents.

Target stage:

**ChatGPT Web HWPX MCP P1 — Document-ID/Object-Store Handoff, Minimal Valid HWPX Materialization & Downloadable Artifact Return**
