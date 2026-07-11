# Troubleshooting

## `MKVMERGE_NOT_FOUND`

Install MKVToolNix, add `mkvmerge` to `PATH`, or set the full executable/directory in `mkvmerge.path`. Run `plexmuxy diagnostics --output diagnostics.zip` to record the detected version.

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

## GUI does not start

Install `plexmuxy[gui]`. On Windows, install the WebView2 Evergreen Runtime. The CLI remains usable without GUI packages.
