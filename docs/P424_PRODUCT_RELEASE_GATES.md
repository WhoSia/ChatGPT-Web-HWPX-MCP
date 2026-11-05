# ChatGPT Web HWPX MCP P4.24 — Native Document Production & Personalized Agent Integration: Hancom-Verified Rendering, Cross-Format Workflows, Adaptive Styling & End-to-End Delivery

**Status:** Development only, not a production release. **Date:** 2026-11-05.
**Source:** `development/p424-native-production-agent-20261105`.
**Parent:** P4.23 native fidelity and personalized-document authoring work.
**Type:** Software product engineering milestone, not a research paper.

## North-star customer experience

A user says: *"Use my existing school/office HWPX template and preferred
document style. Write this content, edit the existing equations, show me a
preview, make corrections and deliver an editable HWPX and a faithful PDF."*

An accepted release fulfills that request without asking the user to
manually construct EqEdit tokens, manage paragraph identifiers or install
a separate renderer they did not request.

## P4.24 gates — order matters

1. **G0: Reliability and code execution.** All Python sources are
   syntactically executable, exact HEAD CI is green, tests prevent fake
   native-PDF receipts and unsafe cross-user editing.
2. **G1: Real Hancom proof.** Authorized Windows installation launches
   `HWPFrame.HwpObject` without hijacking existing documents, opens
   HWPX, emits native PDF via `SaveAs(..., "PDF", "")`, records Hwp.exe
   identity, checks hashes, then compares pages using the same DPI.
   No unreviewed PDF is labeled visually accepted.
3. **G2: End-to-end delivery.** Render/cloud gets a signed, scope-bound
   Windows agent job and the exact PDF bytes land in owner-scoped encrypted
   custody with a durable document revision and a signed delivery link.
   A Windows-only local smoke script is *not* a remote worker protocol.
4. **G3: Personalized production.** User-owned source/template →
   reviewed style candidate → explicit approval → complete in-place
   HWPX edit → native PDF and HWPX preview → user correction and
   revision, all with secure source provenance.
5. **G4: Interoperability and reuse.** At least one verified document
   round-trip with DOCX/PDF input, safe conversion fallbacks and
   reusable template/personal-style rules. Do not implement a parallel
   renderer when validated third-party capabilities exist.

## Early P4.24 actual changes

- Fixed **non-executable Python** in the P4.23 WSL bridge receipt check.
- Staged a trusted local PowerShell helper onto a Windows mount when
  the repository checkout resides in WSL home.
- Added engine, source digest, PDF digest and output-size receipt checks.
- Added an independently runnable WSL handoff regression suite.
- Added a PDF page-level visual comparison script and synthetic tests.
- Audited existing MRI Hancom PDF reference pair: 4 pages in each,
  diff concentrated in pages 2 and 3. These PDFs predate P4.24; they
  do not prove the new Windows script has successfully rendered.

## Source of truth and false-claim guard

- The **P4.23** feature branch, current connected MCP service,
  **P4.24** development branch and Windows Hangul runtime are
  different authorities; never report success in one as success in
  another.
- No latest-commit green CI currently verified for the new P4.24
  branch. An absent workflow run is NOT a pass.
- No actual user-Windows desktop execution has been performed from
  Chat mode. Local Work must execute Windows validation on the user's
  authorized machine.
- Native PDF export is not complete until real Hancom output, page-wise
  review, safe owner-scoped delivery and user download succeed.
- Never publicly commit raw MRI reports, private golden equations or
  identifying document text; a source SHA and anonymous aggregate
  metrics are okay.

## Acceptance files

- `scripts/p423_wsl_hancom_pdf_bridge.py`
- `scripts/p423_hancom_native_pdf.ps1`
- `scripts/p424_pdf_visual_compare.py`
- `tests/test_p424_wsl_native_pdf_bridge.py`
- `tests/test_p424_pdf_visual_compare.py`
- Previously stored owner-approved local Work acceptance packet and
  MRI native reference/edited outputs.

**Do not restart unrelated analysis projects or claim user-facing P4.24
delivery until Gate G0 and G1 are actually completed.**
