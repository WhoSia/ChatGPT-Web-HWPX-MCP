# P4.23 — Real Hancom HWPX to PDF on Windows

## Product promise and current boundary

The feature is a *native Hancom Hangul PDF export*, not a replacement
renderer, PDF-to-HWPX conversion, or a guarantee of page-perfect output.

An installed, licensed Windows Hancom Hangul process exposes the automation
object `HWPFrame.HwpObject`. The converter:
1. Opens the **exact HWPX** through Hangul `Open(path, "HWPX", "")`.
2. Calls `SaveAs(tempPdf, "PDF", "")` (the actual Hangul PDF exporter).
3. Confirms bytes, `%PDF-` header, unchanged source SHA-256.
4. Commits the resulting PDF only if all checks pass and writes a receipt.
5. Closes its own COM object, never globally terminates other user's Hangul
   processes and never disables Hangul security prompts to force success.

## Standalone use on a real Windows/Hancom workstation

Requires Windows PowerShell 5.1 or later, Hancom Office Hangul installed,
a user session allowed to launch the HWP automation COM server, and a local
HWPX file already downloaded from the owned MCP document store.

```powershell
powershell.exe -NoProfile -File .\scripts\p423_hancom_native_pdf.ps1 `
  -InputPath "C:\Users\me\Documents\source.hwpx" `
  -OutputPath "C:\Users\me\Documents\source.pdf" `
  -ReceiptPath "C:\Users\me\Documents\source.pdf.receipt.json"
```

The destination directory must exist. By default, an existing PDF is
*never overwritten*. `-AllowOverwrite` is an explicit Windows-local override.
A successful receipt says `PDF_CREATED_UNREVIEWED`, not `VISUAL_PASS`.

## Python developer API

`hwpx_mcp.custody.p423_hancom_pdf.export_native_hwp_pdf(source, destination)`
returns a bounded receipt with PDF SHA-256, source SHA-256, size and native
engine identifier, and raises a typed error outside Windows or upon failure.

`native_pdf_capability()` distinguishes **Windows OS eligibility** from
installation verification. Successful COM activation and PDF SaveAs must be
observed separately.

## New owner-scoped MCP tool contract (development branch only)

- `get_p423_native_pdf_capability()`: discover the actual host platform.
- `export_p423_owned_hwp_as_native_pdf(document_id, expected_revision)`:
  verify caller ownership and revision, then request native export.
- On Linux/Render returns **`WINDOWS_HANCOM_AGENT_REQUIRED`** and no fake PDF.
- On a licensed Windows MCP host: a PDF up to 4 MiB may be delivered in
  a bounded base64 field with SHA-256 and `NOT_ADJUDICATED` visual status.
  This is a developer-admission path; a real product needs signed binary file
  storage and ordinary downloadable links for larger artifacts.
- Source document revision and ownership must be checked by the server.
  Mere possession of a filename is never sufficient.

**Not yet accomplished:** remote signed Windows agent dispatch, verified
Hangul installed on our runtime, native PDF execution of this exact feature,
PDF signed download/Drive upload, page-by-page PDF review, cross-version
Hancom parity, stable Render release. Existing P4.14 Windows capture/custody
can inform the later remote agent rather than inventing an insecure second
renderer. On any error the system must not claim a native PDF was created.

## Real user acceptance case — MRI

The 2026-11-05 connected MCP generated an MRI acceptance document, and
reused that document as a template for a second HWPX. The source had 13
paragraphs and 2 equations; the template-append result had 17 paragraphs
and 3 equations. Exact original EqEdit scripts were preserved in the
readback. These were *live HWPX generation tests*, not native PDF tests.

The HWPX bytes remain in the authenticated MCP document custody, while the
Drive project folder contains a separate copy of the user-supplied reference
HWPX and a Google Doc receipt. Due to a connector file-reference mismatch,
the newly generated HWPX is **not yet copied to Drive**; do not conflate
the reference copy with the new generated artifact.

## Acceptance criteria

1. Source bytes and SHA match the HWPX revision chosen by the user.
2. COM activates and `SaveAs(..., "PDF", "")` produces a real PDF.
3. No partial output or replacement of an existing file on failure.
4. PDF SHA/size, Hancom installation/build and Windows worker identity in
   audit receipts; do not misrepresent installation if not checked.
5. Convert at least two real MRI/RC HWPX documents with the same Hancom build.
6. Render and visually inspect every page, including equations, tables,
   margins, captions and pagination; require independent acceptance.
7. Deliver the exact signed revision-bound PDF artifact through ordinary
   ChatGPT/Drive UX, without exposing base64 to the end user.
