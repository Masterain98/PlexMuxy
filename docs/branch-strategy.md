# Branch and release strategy

- `main` is the protected, releasable branch.
- `develop` is the integration branch for the next minor release.
- Feature branches start from `develop`, remain short-lived, and merge through reviewed pull requests.
- Release candidates branch from `develop`, pass the full matrix and manual Windows acceptance, then merge to `main` and back to `develop`.
- Tags are immutable and signed when maintainer signing is available. A rollback tag must identify the last known-good pre-migration commit.

Changing `plexmuxy/VERSION` on `main` starts the release workflow; maintainers can also dispatch it manually from `main` to retry a failed run. The workflow creates `v<version>`, publishes the versioned GUI binary directly from `dist` together with the fixed-identity Windows installer, generates a CycloneDX SBOM, release manifest, and SHA-256 list, and publishes the Python distributions through PyPI Trusted Publishing. A retry may refresh assets only when the existing tag points to the same commit; tags remain immutable. Windows signing runs only when the repository certificate secrets are configured; unsigned artifacts remain visibly unsigned rather than pretending a signature exists.

The compatibility aliases `main.py`, top-level `config.py`, `subtitle_utils.py`, and `concurrency.thread_count` remain available through the 0.2 line. They are scheduled for removal no earlier than 0.4, after at least one minor release containing runtime deprecation guidance.
