# Security policy

## Supported code

Only the current released and explicitly verified production deployment is operationally supported. A GitHub `main` commit or green CI job by itself does not establish a deployed or supported release. Consult [PRODUCT_AUTHORITY.md](PRODUCT_AUTHORITY.md) and [docs/RELEASE_OPERATIONS.md](docs/RELEASE_OPERATIONS.md) for the current release boundary.

## Reporting vulnerabilities

**Do not open public issues containing vulnerabilities, credentials, tokens, private documents or database URLs.** Report vulnerabilities privately using the GitHub repository **Security → Report a vulnerability** feature, if enabled, or contact the maintainer through an established private channel. If private reporting is unavailable, create a non-sensitive public request asking for a private reporting channel without publishing exploit details.

Include an affected version/commit, sanitized reproduction steps, expected/actual behavior and impact. Never attach active secrets or confidential HWPX documents.

## Operational controls

- OAuth and data-encryption secrets remain server side. Rotate compromised credentials and review token revocation.
- Treat HWPX as untrusted ZIP/XML input; retain bounded parsing and document ownership checks.
- Confirm revision/CAS guards before mutation; do not treat a generated delivery URL as a consumer-openability certificate.
- Do not expose database branches, backups or rendered documents publicly.
- Use least-privilege production accounts and review dependency advisories.
- Roll back application images with a compatible database state; a code revert is not automatically a data rollback.
