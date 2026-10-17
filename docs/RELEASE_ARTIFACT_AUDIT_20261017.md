# Release artifact and consumer acquisition audit — 2026-10-17

## Verified state

- Exact source and Render LIVE commit: `f50c84409892689e6aec91b3e362ad085f427cab`.
- MIT license recognized by GitHub; this alone is not a license clearance for all bundled components.
- The live MCP produced a temporary HWPX document (revision 1, 7,600 bytes), returned a structurally valid package report and delivered a signed private download URL with the same claimed SHA-256 `2b880191c57f576cb19eb99423856c2adac03504034b6b83672d921d6f8dc432`.
- **External acquisition is NOT VERIFIED.** An independent download attempt in the isolated client environment failed with a network connection error; therefore downloaded bytes, digest match, ZIP integrity on the consumer side and opening the file in Hancom were **not tested**. Receipt generation is not equivalent to consumer acquisition. The temporary document was subsequently deleted successfully.
- GitHub Releases: none published at audit time. No stable v1.0 or certified native-render release claim is authorized by these results.

## Runtime distribution inventory

`Dockerfile` uses `public.ecr.aws/docker/library/rust:1.83-slim`, `node:22-slim`, and `python:3.12-slim`, builds Rust native gates, compiles TypeScript via `npx ... typescript@5.9.2`, installs system Node.js and `requirements.txt`, and **copies the entire `benchmarks/` and `corpus/` trees into the production image**. This broad COPY is a release-material provenance risk; the files cannot be presumed redistributable merely because they are in a public repository.

Direct Python runtime dependencies observed from `requirements.txt`:
- `mcp[cli]==2.2.0`
- `python-hwpx==6.6.0`
- `lxml>=5.0,<7`
- `psycopg[binary]>=3.2,<4`
- `cryptography>=45,<47`
- `olefile>=0.47,<1`
- `Pillow>=11,<13`

**Dependencies are not fully locked**: several use ranges, and this audit did not resolve transitive dependency names/versions/licenses, build an SBOM, collect license notices, or scan the actual deployed image for secrets/artifacts. These operations remain mandatory before distributing an image or an independently downloadable release binary.

## Data and redistribution audit

The repository currently contains metadata/provenance-ledger resources under `fixtures/`, `corpus/` and `benchmarks/`, including P4.21 intake/preregistration files, native capture receipts and dataset registration metadata. This audit enumerated the top-level files but **did not prove redistribution rights for every individual item or all nested resources**. Until a source-by-source rights matrix is signed off, exclude potentially third-party content from any independently distributed release package, or publish source-only without claiming full material clearance.

Additional claims that must stay separate: source CI success, hosted service LIVE SHA, authenticated HWPX mutation/delivery receipts, externally downloaded exact bytes, Hancom native rendering and independent human quality evaluation.

## Release disposition

- `MIT_SOURCE_DISCLOSURE=PASS` (for original works the maintainer is authorized to license).
- `LIVE_SHA=PASS` at observation.
- `SERVER_SIDE_CREATE_AND_DELIVERY_RECEIPT=PASS`.
- `INDEPENDENT_CONSUMER_DOWNLOAD=HOLD_NETWORK_NOT_VALIDATED`.
- `NATIVE_HANCOM_OPEN_AND_VISUAL=HOLD_NO_INDEPENDENT_OBSERVATION`.
- `THIRD_PARTY_LICENSE_CLEARANCE=HOLD_INCOMPLETE_TRANSITIVE_AND_CORPUS_AUDIT`.
- `DISTRIBUTABLE_IMAGE_SBOM_AND_SECRETS_SCAN=HOLD_NOT_PERFORMED`.
- `STABLE_RELEASE=HOLD`.

No release was published, no branch was deleted, and no production database was changed by this audit.
