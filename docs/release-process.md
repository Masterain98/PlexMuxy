# Release and rollback process

The single version source is the plain-text file `plexmuxy/VERSION`. Update that easy-to-find file when preparing a release; `plexmuxy.__version__`, setuptools, the CLI, diagnostics, and the GUI all read it. It is also the intended path trigger for future version-driven CI builds. Release tags must be `v<version>` and the workflow refuses mismatches.

## Candidate release

1. Freeze nonessential features and update `CHANGELOG.md`.
2. Run fast tests, real-media integration tests, wheel clean-install checks, Ruff, mypy, and both PyInstaller builds.
3. Tag `v0.2.0rc1`. The release workflow builds wheel, sdist, Windows CLI/GUI archives, and `SHA256SUMS.txt`.
4. Validate install, GUI startup, matching, Plex track display, cleanup, Unicode paths, and legacy migration on Windows 10/11 and Linux CLI.
5. During observation, accept only data-safety, matching, install/build, migration, and GUI stability fixes.

## Final release

Tag `v0.2.0` only after candidate evidence is recorded. GitHub Release is automated. PyPI publication remains a deliberate maintainer action after artifact/hash comparison.

## Rollback

- Before merging the refactor, tag the old main commit `legacy-pre-refactor`.
- If data safety is affected, mark the GitHub Release as affected and remove its public assets; yank the PyPI version (do not delete release history); publish a prominent warning.
- Revert main to a reviewed commit or the rollback tag without rewriting public history.
- Release a patch version from the last safe point. Never reuse a published version number or tag.
- Require the full data-safety and real-media suites before restoring distribution.
