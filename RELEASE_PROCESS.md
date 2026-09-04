# Release Process

Fast Download Manager uses a strict gated flow so failed ideas never become releases.

```text
IDEA / CODE CHANGE
        |
        v
PR or focused main-branch change
        |
        v
CI TEST GATE
  - install/package discovery check
  - Ruff lint
  - unit + UI tests
  - Windows EXE packaging smoke test
        |
     PASS ONLY
        |
        v
APPLY / MERGE
        |
        v
CREATE VERSION TAG
   vX.Y.Z (must match pyproject.toml)
        |
        v
RELEASE TEST GATE
  - clean environment
  - Ruff
  - Pytest
        |
     PASS ONLY
        |
        v
BUILD / APPLY RELEASE
  - Windows EXE
  - Inno Setup installer
  - package verification
  - SHA-256 checksums
        |
     PASS ONLY
        |
        v
PUBLISH GITHUB RELEASE
```

## Active workflows

Only two workflows are active:

- `.github/workflows/ci.yml` — runs on pushes to `main` and pull requests. It tests first and only then performs the Windows packaging smoke test.
- `.github/workflows/release.yml` — runs only when a `v*` tag is pushed. It validates first, then packages, verifies, and finally publishes the release.

Legacy repair/version-specific workflows have been removed from the active workflow directory so they cannot create duplicate release runs.
