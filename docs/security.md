# Data and archive safety

PlexMuxy treats source media as irreplaceable.

- In-place muxing is rejected even when overwrite is enabled.
- Existing outputs require overwrite opt-in. Muxing still uses a unique temporary path, so a failed subprocess cannot corrupt the previous output.
- Delete cleanup and font-directory deletion require confirmation. Verification failure, cancellation, partial batch failure, and missing attachments suppress cleanup.
- `move` never overwrites an `Extra` file; it creates `name (1).ext`, `name (2).ext`, and so on.
- Saved plans are untrusted input. Absolute paths, tracked file metadata, recomputed output paths, configuration hashes, attachment containment, newly appeared outputs, and SHA-256 digests for subtitles/fonts/font archives are checked before execution.
- ZIP/7z members are checked for path traversal and configurable size/count/depth limits before extraction. RAR is denied by default when metadata cannot be safely inspected.
- Subset fonts and rewritten subtitles are created only under an execution-scoped system temporary directory, written through temporary names, reopened and validated, and removed after every mux worker exits. They are never added to user cleanup candidates.
- Ambiguous font matches, missing glyphs, unsafe ASS/SSA structures, and ambiguous legacy encodings cannot silently enter the subset pipeline. Full-font fallback is limited to explicit policy branches.
- Diagnostic archives contain no media and redact configured directories.
- Dependency paths selected or saved through the GUI must pass a short, no-shell functional probe. An invalid explicit path stays authoritative and is never replaced by a same-named binary from another source.
- Windows UnRAR acquisition is restricted to `https://www.rarlab.com/`, enforces a 10 MiB limit and timeouts, writes through a temporary file, and requires a valid Authenticode publisher matching win.rar GmbH/RARLAB before atomic publication of the installer. The official interactive installer is used because RARLAB does not publish a stable unattended extraction contract; a failed download, signature check, install, or final UnRAR probe never changes the saved configuration or an existing managed tool.

Treat any report of unintended overwrite, move, or deletion as release-blocking. Stop distribution, mark the release as affected, publish a warning, reproduce using copies, and ship a patch only after the data-safety regression suite passes.
