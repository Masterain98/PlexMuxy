# Changelog

All notable changes follow Keep a Changelog categories.

## [Unreleased]

### Added

- Immutable, serializable plan snapshots and `execute-plan`.
- Versioned config migration, atomic config saving, backup reports, and diagnostics export.
- Background GUI jobs with progress, cancellation, accessible live status, and safe DOM construction.
- Crowdin-compatible JSON localization with an English source catalog and Simplified Chinese translations.
- Real-media integration suite, multi-platform/Python CI, coverage, static checks, wheel verification, PyInstaller release builds, and SHA-256 generation.
- ASS/SSA referenced-font discovery, archive resource limits, conflict handling, and source-track plan metadata.
- Conservative source-audio filtering with manual track overrides and exact output verification.
- Safe plan editing, external track reassignment/order, subtitle metadata editing, and ffmpeg audio previews.
- Persistent SQLite task queue/history, crash interruption state, retries, replanning, and per-task diagnostics.
- Task diagnostics now expose the unredacted media/project root path so troubleshooting agents can locate the original media resources.
- Validated persistent font-subset cache and ffmpeg/libass render integration tests.
- Opt-in update checks and post-verification Plex library refresh with environment-only token handling.
- English/Simplified Chinese CLI messages with stable JSON output and error contracts.
- Font attachment MIME mode setting (`font.mime_mode`) letting users choose the legacy (`application/x-truetype-font`, `application/vnd.ms-opentype`) or modern (`font/ttf`, `font/otf`, `font/collection`) MIME scheme written into MKV files.
- Standardized setting compatibility layer (`plexmuxy/compatibility.py`) that declares each version-gated setting's required tool version in a compact notation (e.g. `mkvmerge>=66`); the GUI now automatically disables options whose environment requirements are unmet (the modern font MIME mode requires mkvmerge v66+).
- Fixed-identity Windows installer, restricted notification activation, SBOM, release manifest, optional signing, and PyPI Trusted Publishing workflow.

### Changed

- Replaced the unmaintained `pymkv` distribution with `pymkv2` while preserving the `pymkv` runtime import API.
- Redesigned the desktop GUI around the five-stage workflow, persistent themes, responsive navigation, and clearer task states.
- Matching now performs global confidence assignment and skips ambiguity by default.
- Muxing uses cancellable subprocesses, temporary outputs, structural verification, and bounded concurrency.
- Source tracks remain preserved by default; filtering is explicit and fails closed when inspection is unavailable.

### Fixed

- Prevented pywebview from recursively inspecting the native GUI window by exposing only the intended bridge methods.
- Made sidebar selection transitions target the clicked stage directly instead of cycling through every item.
- Prevented movie fallback across multi-video directories.
- Prevented cleanup before output verification and premature cleanup of shared resources.
- Prevented failed or partial mux output from replacing a valid destination.

### Security

- Added plan tamper/staleness checks, archive traversal/resource defenses, atomic writes, and double confirmation for destructive actions.

### Deprecated

- `main.py`, top-level `config.py`, `subtitle_utils.py`, and legacy `thread_count` configuration.
