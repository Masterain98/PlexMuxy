# Data and archive safety

PlexMuxy treats source media as irreplaceable.

- In-place muxing is rejected even when overwrite is enabled.
- Existing outputs require overwrite opt-in. Muxing still uses a unique temporary path, so a failed subprocess cannot corrupt the previous output.
- Delete cleanup and font-directory deletion require confirmation. Verification failure, cancellation, partial batch failure, and missing attachments suppress cleanup.
- `move` never overwrites an `Extra` file; it creates `name (1).ext`, `name (2).ext`, and so on.
- Saved plans are untrusted input. Absolute paths, tracked file metadata, recomputed output paths, configuration hashes, attachment containment, and newly appeared outputs are checked before execution.
- ZIP/7z members are checked for path traversal and configurable size/count/depth limits before extraction. RAR is denied by default when metadata cannot be safely inspected.
- Diagnostic archives contain no media and redact configured directories.

Treat any report of unintended overwrite, move, or deletion as release-blocking. Stop distribution, mark the release as affected, publish a warning, reproduce using copies, and ship a patch only after the data-safety regression suite passes.
