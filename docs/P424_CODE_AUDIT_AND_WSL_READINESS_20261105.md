# P4.24-R2 — Coding MCP/skill audit, native PDF and WSL readiness

**Scope:** development branch `research/p423-native-equation-corpus-20261031`;
selected native PDF, WSL, P4.14 trust, MCP export and benchmark files.
Not a claim of whole-repository line-by-line or native visual verification.

## MCP-Hub tooling evaluated

- `hub_discover_reviewed_skills(code/testing/debugging)`: Ponytail 5.3.3,
  Superpowers systematic debugging/TDD and Vercel React best practices.
  All were **pinned-source metadata only**, not installed or executable
  skills in this chat. No silent install or user-directory mutation.
- `hub_plan_public_skill_bundle(codex)`: review-required plan only, no
  installer launched. The upstream pin does not make later install commands
  immutable: review versions, scripts, hooks and permissions.
- `hub_analyze_public_unified_diff`: successfully counted a
  synthetic public patch, not an executable review or semantic verdict.
- `hub_compare_public_json_shapes`: compared synthetic public preflight
  versus native-receipt shapes; structural summary only, not a validator.
- GitHub/Notion connectors: actual source readback, reviewable commits,
  author/committer inspection and durable engineering record.

## Findings by risk and status

| Priority | Finding | Evidence | Resolution / next gate |
| --- | --- | --- | --- |
| Critical | WSL bridge accidentally contained literal backslash-n in Python subprocess statement; runtime import fails | `scripts/p423_wsl_hancom_pdf_bridge.py` history | **FIXED** at `070ed94d`, source-integrity test added |
| High | WSL identification accepted user-controlled `WSL_DISTRO_NAME` on generic Linux | same bridge `on_wsl()` | **FIXED** at `5750d3bb`; spoof regression at `5dbd631f` |
| High | Native PDF exporter has **no independent visual review or signed cloud receipt** | `p423_hancom_pdf.py`, `p423_pdf_mcp.py` | **OPEN**: P4.14 trusted capture, human page review and delivery required |
| High | P4.23 PowerShell checks a new Hwp.exe PID, but timing alone may not prove COM object's exclusive ownership of that process under a concurrent startup | `scripts/p423_hancom_native_pdf.ps1` | **OPEN**: production must use job-scoped P4.14 authority, test races on Windows; do not infer strict process ownership from PID appearance alone |
| High | User-supplied benchmark PASS claims were called `verified_matched_pairs` despite no independent evidence check | `scripts/p424_competitor_benchmark.py` | **FIXED**: `declared_pass_matched_pairs` and `independent_evidence_verified: false` |
| Medium | Direct `python scripts/p424_wsl_hancom_preflight.py` could fail because package import relied on repository root in `sys.path` | preflight entrypoint | **FIXED**: direct-script and package imports supported, subprocess CLI test |
| Medium | Basic HWPX preflight could pass a fake 200-byte PK prefix | preflight | **FIXED**: ZIP central-directory check using `zipfile.is_zipfile` |
| Medium | WSL may leave failed PDF/receipt in shared Windows directory | WSL bridge/PS output model | **OPEN**: deliberate no-overwrite, job isolation and forensic quarantine design before user retry |
| Medium | Output existence and checksum check are not an atomic signed handoff; local files remain mutable after audit | WSL bridge, MCP base64 path | **OPEN**: bind signed revision/SHA to immutable owner-scoped PDF custody |
| Medium | Windows installation / actual COM SaveAs and all-page visual quality cannot be tested on Linux Render | acceptance requirements | **OPEN**: authorized real Windows/Hancom workstation required |

## Implemented WSL foundation

- `scripts/p424_wsl_hancom_preflight.py`: read-only, no PowerShell
  execution or COM activation, bounded source size, ZIP container sanity,
  Windows mount and command availability checks, vacant PDF/receipt names.
- `tests/test_p424_wsl_hancom_preflight.py`: synthetic source checks,
  read-only status, missing commands, stale outputs, direct CLI invocation.
- `tests/test_p424_script_import_integrity.py`: AST parse gates for
  WSL/native-export/benchmark Python paths.
- `docs/P424_WSL_WINDOWS_HANCOM_ACCEPTANCE.md`: explicit
  WSL→local Windows smoke→P4.14 signed evidence→delivery trust boundaries.

## Acceptance state: not promoted

No actual WSL/Windows native export was run in this chat; no user-owned
Windows files or Hancom installation were accessed. GitHub CI for the
latest specific commit must be inspected separately before promotion.
The source changes on this research branch are not `main` and do not
change Render. Do not declare runtime PASS from these audit tests.

## Next engineering gate

1. Exact-head CI and Python compile/test discovery results.
2. Local Windows user-approved smoke after read-only preflight.
3. P4.14 signed capture job/receipt, with process ownership and concurrency
   checks and explicit trust verification; no synthetic signature promotion.
4. All-page rendering and MRI 70-equation/9-manual-correction evaluation.
5. Immutable owner-scoped PDF custody, signed download and consumer readback.

**Ponytail principle applied**: prefer smallest verified change within
existing components; do not fork a second renderer or import unreviewed
third-party code into the production service.
