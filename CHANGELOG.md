# Changelog

All notable changes follow Keep a Changelog categories.

## [Unreleased]

### Added

- Immutable, serializable plan snapshots and `execute-plan`.
- Versioned config migration, atomic config saving, backup reports, and diagnostics export.
- Background GUI jobs with progress, cancellation, accessible live status, and safe DOM construction.
- Real-media integration suite, multi-platform/Python CI, coverage, static checks, wheel verification, PyInstaller release builds, and SHA-256 generation.
- ASS/SSA referenced-font discovery, archive resource limits, conflict handling, and source-track plan metadata.

### Changed

- Matching now performs global confidence assignment and skips ambiguity by default.
- Muxing uses cancellable subprocesses, temporary outputs, structural verification, and bounded concurrency.
- Source tracks are preserved by default; filtering remains opt-in future work.

### Fixed

- Prevented movie fallback across multi-video directories.
- Prevented cleanup before output verification and premature cleanup of shared resources.
- Prevented failed or partial mux output from replacing a valid destination.

### Security

- Added plan tamper/staleness checks, archive traversal/resource defenses, atomic writes, and double confirmation for destructive actions.

### Deprecated

- `main.py`, top-level `config.py`, `subtitle_utils.py`, and legacy `thread_count` configuration.
