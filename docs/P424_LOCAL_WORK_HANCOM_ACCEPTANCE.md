# P4.24 — Local ChatGPT Work acceptance procedure (Windows + WSL)

**Use on the owner's authorized Windows computer with an already installed,
licensed Hancom Office Hangul.** Chat-mode cloud does not have authority or
access to start the user's Hwp.exe. The Work operator must not bypass license,
automation trust or interactive security prompts.

## Objective

Prove a *real* HWPX→PDF conversion using the installed Hangul executable,
compare every PDF page against an explicitly selected approved baseline,
and return an evidence report. This is G1 of the P4.24 release plan.

## Before executing

1. Verify that you are in the **correct user's workspace** and the HWPX
   source and expected PDF are specifically approved for the local test.
2. The GitHub branch must be `development/p424-native-production-agent-20261105`.
3. Run on WSL with Windows interop enabled, but place source HWPX, baseline
   PDF and output directory on a Windows drive mounted under `/mnt/<letter>/`.
4. Do not kill, overwrite, save or close any unrelated open Hangul window.
   The automation script refuses to operate when it cannot prove it owns
   its newly launched Hwp.exe. If no clean process can be owned, **stop**.
5. Preserve original HWPX/PDF and SHA-256. Do not upload whole personal
   documents or raw EqEdit excerpts to public GitHub.

## One-command acceptance

```bash
python3 -m pip install --user pymupdf
mkdir -p /mnt/c/p424-validation/run01
python3 scripts/p424_local_hancom_acceptance.py \
  "/mnt/c/path/to/source.hwpx" \
  --output-dir "/mnt/c/p424-validation/run01" \
  --baseline-pdf "/mnt/c/path/to/user-accepted.pdf"
```

Expected products in the fresh output directory:
- `source.native-hancom.pdf` — created by real Hwp.exe `SaveAs(PDF)`;
- `source.native-hancom.pdf.receipt.json` — COM engine and exact binary receipt;
- `source.p424-acceptance.json` — signed-input hashes, output digest, all-page
  pixel comparison, **REQUIRES_HUMAN_PAGE_REVIEW** status.

If `pip` is unavailable in WSL, set up a permitted project venv; never change
the Windows Hangul installation or execution policies to make tests pass.

## Human acceptance (mandatory)

Open both PDFs and inspect every page for:
- fonts, inline EqEdit variables, upright descriptive subscripts;
- `cases` columns and baseline alignment;
- equation boxes, `left/right` delimiters, punctuation and spacing;
- table/caption/paragraph overflows, page breaks and margin shifts.

Use the 9 approved MRI equation corrections (indices 13, 23, 33, 34, 35,
37, 46, 50, 53) as **private** regression checks when a full original
MRI report is used. A grayscale diff is a triage signal only, not an
automatic PASS.

## Failure and reporting protocol

- A Python syntax error or test failure is a **code regression**.
- Missing `HWPFrame.HwpObject` is **native environment unavailable**.
- Wrong owner, altered SHA or missing source is a **provenance failure**.
- Failed `SaveAs(PDF)` or invalid `%PDF-` is a **conversion failure**.
- Suspected page defect is a **visual acceptance HOLD**.
- No result artifacts means **NOT_EXECUTED**, not PASS.
- Never copy local source reports to GitHub without explicit permission.

Return a compact report: exact branch+HEAD, Windows and Hancom version,
document SHA and byte counts, PDF page count, per-page visual diff summary,
native export success/failure, issues by page, and user-approved fixes.
Store all original bytes in the user's private Drive folder, not the
public repository. Publish only anonymized failure repros with permission.

## Release rule

A local successful Hwp.exe SaveAs export proves the **desktop converter path**,
not cloud delivery. The signed P4.14 Windows-worker relay, owner-scoped PDF
custody and delivered artifact must be separately tested before any P4.24
production rollout.
