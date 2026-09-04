# Release Process

Fast Download Manager uses a gated release process.

```text
Idea / code change
        |
        v
   Pull Request / push
        |
        v
CI validation
  - lint
  - unit tests
  - UI tests
  - Windows packaging smoke test
        |
     PASS only
        v
Version tag (vX.Y.Z)
        |
        v
Release validation
        |
        v
Windows EXE + Inno Setup installer
        |
        v
Package verification + SHA-256
        |
        v
GitHub Release publish
```

Only `.github/workflows/ci.yml` and `.github/workflows/release.yml` are active workflows. Legacy repair/version-specific workflows are not part of the release path.
