# Contributing

Thank you for your interest in ChatGPT Web HWPX MCP.

## Project maintenance

This is currently a sole-maintainer project. Proposed fixes can be discussed through issues or pull requests, but **there is no promise of response time or automatic merge**. All accepted changes must pass the relevant tests and licensing/provenance review. The maintained GitHub commit attribution policy currently requires final commits to be authored and committed by `WhoSia`. Automated services can test and build but must not commit or add bot coauthor trailers. Outside proposals should be attributed accurately in PR discussion; no one should misrepresent authorship.

## Local development

Use Python 3.12 and an isolated environment. Install `requirements.txt` and `requirements-dev.txt`; see the README and operations runbook. Keep production credentials and private HWPX files out of Git.

For focused changes, run tests relevant to the touched modules. Before changing runtime behavior, run the main lifecycle/fidelity regression and validate packaging/import changes against the exact Docker image when infrastructure allows.

## Review and evidence

- Explain the problem, scope, expected behavior and backward compatibility.
- Add regression tests for user-facing changes.
- Do not claim Hancom-native visual fidelity without independent native rendering evidence.
- Include a disclosure when an external corpus or fixture has unclear usage or redistribution rights.
- Never submit client secrets, authorization headers, private personal documents, database exports or active signing keys.
- A CI success does not prove a Render deployment. Record actual service health/SHA separately.
- Follow [SECURITY.md](SECURITY.md) for sensitive reports.
- Keep branch deletion manual; preserve requested recovery refs.

## Licensing of contributions

Only submit content that you have the right to contribute under [MIT](LICENSE). Identify third-party inputs and preserve required notices. Third-party fixtures may require separate licenses and must never be silently relicensed.
