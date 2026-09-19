# Legacy HWP 5.x Read-Lane Ledger

## Scope

This is preparatory functionality for P3.5, not a claim of full HWP fidelity.

## Implemented

### Native HWP 5.x reader

`hwp5_reader.py` parses:

- OLE/CFB `FileHeader`
- HWP 5.x version
- compression/security flags
- `BodyText/Section*` streams
- HWP record headers
- `HWPTAG_PARA_TEXT` text records
- optional `PrvText`

Compressed body streams are decoded using raw DEFLATE semantics.

### Security boundary

The native reader does not bypass:

- password encryption
- DRM
- certificate encryption

Such inputs are reported as unreadable instead of being decrypted or guessed.

### MCP surfaces

`inspect_hwp5_document`

- bounded base64 ingress
- source SHA-256
- header/version/flags
- body paragraph text
- explicit `READ_ONLY_LOSS_AWARE` authority

`materialize_hwp5_text_derivative`

- creates a new editable HWPX derivative from extracted HWP text
- records source HWP SHA-256, filename, version, flags and warnings
- never mutates the original HWP binary
- labels fidelity as `text-only`

## Explicit non-claims

The current HWP lane does not yet claim faithful preservation of:

- page geometry
- paragraph/character styling
- tables
- equations
- images/drawing objects
- headers/footers
- fields/controls
- distribution-document semantics

## Evidence

Primitive tests cover:

- HWP 5.x signature/version/flag decoding
- record framing
- PARA_TEXT extraction
- raw DEFLATE decompression
- control-unit filtering

Integrated lifecycle CI has passed with both HWP MCP tools present in native tool discovery.

## Dependency policy

The implementation uses the published HWP binary structure directly and a small OLE/CFB dependency. It does not incorporate the AGPL `pyhwp` codebase.

## Successor

P3.5 should replace the current text-only intermediate result with a common document IR shared by HWP and HWPX, then add fidelity grades per object family before any richer HWP→HWPX promotion is authorized.
