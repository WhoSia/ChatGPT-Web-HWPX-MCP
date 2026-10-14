# Third-party material and licensing boundary

The root [MIT license](LICENSE) applies only to original repository software and documentation for which the copyright holder has authority to grant MIT rights. It does **not** relicense dependencies, upstream projects, trademarks, institutional documents, sample HWPX files or other third-party data.

## Runtime dependencies

Runtime packages include `mcp[cli]`, `python-hwpx`, `lxml`, `psycopg[binary]`, `cryptography`, `olefile` and `Pillow`; the production Docker image also installs Node.js/Rust tooling and any transitive dependencies. Their own package license notices and applicable attribution/distribution obligations govern them. Consult the pinned lock or installed package metadata for each shipped release; do not infer that everything is MIT licensed because the root project is.

## Fixtures, corpora, and external content

Files in `fixtures/`, `corpus/`, `benchmarks/`, `docs/`, and test resources may contain source-derived, government, institutional, academic or third-party HWPX/XML/text artifacts. Their origin, license and redistribution eligibility must be checked item by item **before** bundling an installer, public binary release or downloadable corpus. Public download availability alone is not redistribution permission. P4.21 external-acquisition evidence is not permission to redistribute source bytes.

## Brand and user documents

Hancom, HWP and HWPX names and related trademarks belong to their respective owners. The project is independently maintained and does not claim Hancom endorsement. Documents processed by the MCP server remain governed by their owners' rights and confidentiality; user content is not relicensed by this repository's MIT license.

## Release checklist

Before distributing a release archive or container: generate an exact dependency/SBOM inventory; verify third-party package licenses and required notices; audit every bundled fixture or corpus item; exclude credentials, secrets, private documents, telemetry and database backups; retain the original MIT copyright notice; and link the final source SHA, build digest and production verification record.

If provenance or rights are unresolved, omit that material from distribution and document the hold.
