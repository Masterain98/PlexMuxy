# Troubleshooting

## pytest temporary-directory errors on Windows

Keep Python's system temporary directory separate from pytest's `--basetemp` directory. Pointing both at the same path lets pytest try to remove a directory that the Python process is actively using and causes misleading `PermissionError` or `WinError 32` setup failures.

Use the repository helper:

```powershell
./scripts/test-local.ps1
```

The helper creates `.pytest-tmp/<process-id>/system` for `TEMP`/`TMP` and `.pytest-tmp/<process-id>/pytest` for pytest. On Linux and macOS, use `./scripts/test-local.sh` with the same separation. Both paths are ignored by Git.

## `MKVMERGE_NOT_FOUND`

Install MKVToolNix and choose GUI → Environment configuration → mkvmerge → Auto-detect. On Windows, PlexMuxy checks the MKVToolNix uninstall registry information before `PATH`, then validates `mkvmerge --version`. You can also set the executable/directory in `mkvmerge.path` or use Browse. An invalid explicit path is reported instead of silently falling back to a different binary. Run `plexmuxy diagnostics --output diagnostics.zip` to record the detected version.

## UnRAR could not be acquired

The RARLAB action is available only on Windows x64. PlexMuxy downloads the official signed installer, waits for its UI to finish, and then probes the installed `UnRAR.exe`. If the installer is cancelled or UnRAR is not found, finish the official installation and click Auto-detect. Downloaded installers are stored under `%LOCALAPPDATA%\PlexMuxy\tools\downloads`; no path is saved until Save environment is clicked.

## No plan was generated

Review `skipped_files`. Common reasons are `already_processed`, `unmatched`, `ambiguous_match`, `unmatched_language`, `missing_referenced_font`, and `no_mux_inputs`. Rename files or adjust the explicit matching policy; do not enable movie fallback for multi-video directories.

## `PLAN_STALE`

An input/config changed or an output appeared after preview. Regenerate the plan. Never edit plan JSON to bypass the check.

## Output already exists

Choose another suffix/output directory, or review the existing file and explicitly enable overwrite. The source path can never be the output path.

## Output verification failed

The error code identifies an invalid container, missing track, property mismatch, or missing attachment. The source remains untouched. Inspect the `.failed` output and diagnostic report before retrying.

## Delete requires confirmation

Pass `--yes` only after reviewing the plan. The GUI presents a destructive-action confirmation.

## Font archive errors

Corrupt archives, resource-limit violations, path traversal, and uninspectable RAR files are reported. Extract RAR fonts manually into `Fonts`, or explicitly opt into uninspected extraction only for trusted archives.

## `font_subset_blocked` or `FONT_SUBSET_FAILED`

Planning blocks a video when a font is missing or ambiguous, a selected face lacks required characters, or the ASS/SSA structure cannot be analyzed and rewritten safely. BOM-less byte sequences that are both valid GB18030 and CP932 but decode differently are intentionally rejected. Use a correctly encoded/BOM-tagged subtitle, install the exact referenced font, or choose a documented `missing_font_action`; do not rename an unrelated font to bypass matching.

At execution time, `FONT_SUBSET_FAILED` means a previously matched source changed or a verified runtime subset/rewrite could not be produced. The default `subset_failure_action=fallback-full` applies only to a concrete matched family that cannot be subset safely. `skip-video` isolates the affected video and `fail-job` stops the batch before any mux process starts.

## A diagnostic path did not fit in the title bar

Transient results such as diagnostics export paths now appear in a wrapping toast with an “Open folder” action. The title bar is reserved for persistent state such as a missing required dependency and an active job.

## Windows notification is unavailable

Notifications require the Windows GUI build, its packaged ICO, and the pywebview Windows runtime. Use the test button on Environment configuration. The setting is disabled when capability detection fails; mux completion is unaffected. The current backend is a Windows Shell notification-area balloon, not an actionable Windows App SDK notification with application activation.

## GUI does not start

Install `plexmuxy[gui]`. On Windows, install the WebView2 Evergreen Runtime. The CLI remains usable without GUI packages. If file dialogs scale incorrectly, use the packaged GUI whose manifest requests Per-Monitor V2 awareness rather than launching an older wrapper executable.
