# P4.24-R2 — WSL-to-Windows Hancom acceptance handoff

**Status:** development-only, user-run local acceptance; not production native authority.

## Authority boundaries

| Layer | Responsibility | Cannot claim |
| --- | --- | --- |
| WSL static preflight | Check OS, mounted paths, tools, input signature/size, vacant output names | Hancom installation, licensed COM, rendered document |
| P4.23 WSL smoke bridge | Invoke a user-approved Windows PowerShell COM job on explicit paths; compare source/PDF SHA and receipt | Ed25519 signed P4.14 evidence, visual PASS or online delivery |
| P4.14 signed capture worker | Validate a bounded job, control owned Hangul processes, sign receipts with local Ed25519 key, bind exact head/build/source | Per-document user review without separate adjudication |
| P4.24 future delivery | Owner-scoped immutable PDF custody, signed download and independently checked re-open | Unverified artifact becoming production PASS |

**Never treat P4.23 local receipt as a signed P4.14 receipt.**
P4.14 uses schema `chatgpt-web-hwpx-mcp/p414/distributed-native-capture/v1`,
`product=0.39.0-p4.14`, exact-head and source manifest fields; do not
forge/adapt the older schema or bypass `verify_signed_receipt`.

## Read-only WSL readiness

On a Windows laptop with licensed Hancom Office, working WSL interop and
an **approved local checkout under `/mnt/c/...`**, use a non-sensitive
test fixture first. Input and output files, and the PowerShell companion
script, must be on real Windows-mounted drive paths.

```bash
python3 -m compileall -q scripts/p423_wsl_hancom_pdf_bridge.py \
  scripts/p424_wsl_hancom_preflight.py
python3 -m unittest -v \
  tests.test_p423_wsl_hancom_pdf_bridge \
  tests.test_p424_wsl_hancom_preflight \
  tests.test_p423_hancom_pdf \
  tests.test_p423_pdf_mcp

python3 scripts/p424_wsl_hancom_preflight.py \
  /mnt/c/approved-fixtures/sample.hwpx \
  /mnt/c/approved-results/sample.native.pdf
```

Preflight is **read-only**: it does not run PowerShell, call COM,
change a source file, create an output, or test the Hancom installation.
A `READY_FOR_MANUAL_SMOKE` result is an eligibility signal only.

## Separate, explicit native smoke test

Only after owner approval and a preflight result without issues, execute
the existing dedicated script on the authorized workstation:

```bash
python3 scripts/p423_wsl_hancom_pdf_bridge.py \
  /mnt/c/approved-fixtures/sample.hwpx \
  /mnt/c/approved-results/sample.native.pdf
```

No automatic retry, background watcher, systemwide Hwp.exe kill, or
silent LibreOffice renderer fallback. Use a **new** output+receipt filename
for any retry; never overwrite a failed trial without examination.

The result `PDF_CREATED_UNREVIEWED` means the worker reported SaveAs and
the WSL wrapper checked selected bytes. It does not prove visual or
semantic fidelity. Review **all** pages and compare native EqEdit
renderings. Real MRI corpus (70 equations, 9 human-corrected differences)
remains private in owner-controlled evidence storage.

## Required redacted evidence checklist

- Source SHA-256 and exact owned revision (outside public logs).
- P4.23 output SHA-256, PDF length, script/source commit and return code.
- Windows build, Hwp.exe executable SHA, product/file version and job PID.
- Page count, independently observed page images and reported defects.
- Whether P4.14 issued an independently verified signed receipt.
- Exact user-received output SHA and successful independent open.
- Separate statuses: structural pass, native conversion, visual review,
  cryptographic signature, delivery and consumer-openability.

Never commit personally identifiable HWPX sources, machine paths, signing
secrets, PDF pages, expired private download URLs or private keys.

## Audit findings and follow-up gates

1. **CRITICAL — fixed at 070ed94d:** prior WSL subprocess statement
   contained a literal backslash-n and did not compile; source-level
   import/compile gates are necessary.
2. **HIGH — unresolved:** P4.23 local untrusted receipt is not a signed
   P4.14 envelope; prevent production ingestion, continue through P4.14.
3. **HIGH — unresolved:** WSL smoke does not independently visually inspect
   PDFs or deliver immutable owner-scoped bytes.
4. **MEDIUM — unresolved:** WSL failure may leave a partial PDF and receipt.
   Preserve for operator diagnosis, never treat as approved or retry with
   existing paths. A future job-scoped quarantine mechanism should avoid
   deleting artifacts belonging to a different process.
5. **MEDIUM — test gate:** build environment and Windows COM activation
   cannot be inferred from Linux CI or mocked tests.
6. **MEDIUM — product debt:** the standalone worker and MCP inline-base64
   path duplicate parts of the older signed capture path; retire shortcuts
   when proper job-scoped binary delivery is verified.

This gate is intended to support real Hancom testing, not substitute for it.
