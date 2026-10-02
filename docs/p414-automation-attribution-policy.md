# P4.14 Automation Attribution Policy

This policy repairs future automation attribution without rewriting release history.

- Release and maintenance commits on `main` are authored and committed by the responsible human maintainer.
- GitHub Actions workflows are read-only with respect to repository contents. They validate, build, and upload workflow artifacts; they do not create or push commits.
- Changes produced by automation are proposed as patches or pull requests and are reviewed and merged by a human maintainer. No auto-commit action or bot identity is used as a substitute for that review.
- Workflows that need additional permissions must declare the narrowest required permission explicitly and must not gain `contents: write` merely to publish a commit.
- Existing commit objects, P4.12/P4.13 release records, and their ancestry are not rewritten to alter contributor attribution. The noncanonical `d8caed3` history remains preserved by the backup tag and is not part of canonical `main`.

All workflows currently lacking an explicit permission block now declare `contents: read`; workflows with an existing permission block retain their narrower declared permissions.
