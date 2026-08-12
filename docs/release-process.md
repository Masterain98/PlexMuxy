# Release and rollback process

The single version source is the plain-text file `plexmuxy/VERSION`. `plexmuxy.__version__`, setuptools, the CLI, diagnostics, GUI, Windows executable metadata, installer, and release workflow all read that value. Use PEP 440-compatible versions such as `0.2.1`, `0.2.1rc1`, `0.2.1b1`, or `0.2.1a1`; release tags are always `v<version>`.

## Triggering a release

- Bump `plexmuxy/VERSION` and merge that change to `main` for a new release. The path change starts the release workflow automatically.
- Use the release workflow's **Run workflow** action on `main` to retry a failed run without changing the version file again.
- A retry may replace assets only when the existing `v<version>` tag points to the same commit. If it points elsewhere, the workflow fails and requires a new version instead of moving an immutable published tag.

## Candidate release

1. Freeze nonessential features, update `CHANGELOG.md`, and set a candidate version such as `0.2.1rc1`.
2. Run fast tests, real-media integration tests, wheel clean-install checks, Ruff, mypy, and both PyInstaller builds.
3. Merge the version change to `main`, or manually dispatch the workflow from `main` if the automatic run needs to be retried.
4. Validate install, GUI startup, matching, Plex track display, cleanup, Unicode paths, and legacy migration on Windows 10/11 and Linux CLI.
5. During observation, accept only data-safety, matching, install/build, migration, and GUI stability fixes.

## Final release

After candidate evidence is recorded, set the final version such as `0.2.1` and merge it to `main`. The workflow creates the `v<version>` GitHub Release with generated notes, then publishes the wheel and source distribution to PyPI through Trusted Publishing.

The GitHub Release uploads the files at the root of `dist`, including the versioned Windows GUI binary, per-user installer, wheel, source distribution, CycloneDX SBOM, `release-manifest.json`, and `SHA256SUMS.txt`. ZIP packaging is not required. Code signing is applied only when the repository certificate secrets are configured.

## Rollback

- Before a migration release, keep a rollback tag for the last known-good commit.
- If data safety is affected, mark the GitHub Release as affected and remove its public assets; yank the PyPI version (do not delete release history); publish a prominent warning.
- Revert `main` to a reviewed commit or the rollback tag without rewriting public history.
- Release a patch version from the last safe point. Never reuse a published version number or move a published tag.
- Require the full data-safety and real-media suites before restoring distribution.
