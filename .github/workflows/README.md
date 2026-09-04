# CI/CD workflow policy

The repository intentionally keeps only two active workflows:

- `ci.yml` — every push/PR: lint, tests, then Windows packaging smoke test.
- `release.yml` — version tags only: validate first, then build the Windows EXE + installer, verify them, and publish the GitHub release.

Legacy repair and version-specific workflows have been removed to prevent duplicate runs and conflicting release pipelines.
