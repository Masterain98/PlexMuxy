# Architecture

```text
CLI / GUI
    ↓
Service (plan snapshot, progress, cancellation, bounded concurrency)
    ↓
Scanner → Matcher → Planner → ASS analysis → Font face matching
    ↓                 ↓                         ↓
Archive/font safety   Source-track inspection   Immutable subset intent
                                                  ↓
                         Execution workspace → subset + alias rewrite + validation
    ↓
Mux subprocess → Structural verifier → Batch cleanup
```

The adapters validate user payloads and call `plexmuxy.service`; they do not implement mux policy. `scanner` classifies files without following symlinks or hidden paths by default. `matcher` globally assigns each candidate so a file cannot silently attach to two videos. `planner` creates deterministic outputs, tracks, attachment intent, and cleanup candidates.

`snapshot` records the normalized config plus size and nanosecond modification time for every input. Schema 2 also records SHA-256 digests for subtitles, fonts, and font archives, together with deterministic subset intent; generated workspace paths are never serialized. Execution validates the snapshot and rechecks output appearance. Deserialization requires absolute paths and reconstructs typed models; output paths are recomputed from the saved configuration to reject edited plan paths.

Subset execution is deliberately two-phase. `ass_analysis`, `font_catalog`, and `font_matching` produce immutable intent during planning. After snapshot validation, `font_prepare` materializes archive members, subsets every selected face, validates cmap/name/style metadata, and rewrites temporary ASS/SSA files. Every plan must finish preparation before the bounded mux pool starts. `SubsetWorkspace` owns all generated files and removes them only after every mux worker exits.

`muxer` owns the `mkvmerge` subprocess so cancellation can terminate it. It never writes directly to the final pathname. Prepared runtime plans replace only subtitle and attachment inputs while results retain the original immutable plan. `verify_mux_output` parses `mkvmerge -J`, distinguishes execution and verification error codes, and verifies expected structure, attachment names, and MIME types. `cleanup` operates once, after all jobs settle, using dependency groups for shared files.

The GUI `PlexMuxyApi` starts daemon-backed jobs and exposes `start_job`, `get_job_status`, `get_job_report`, and `cancel_job`. Progress events include preparation, family, mux, verification, and cleanup phases; the core package has no GUI dependency. Persistent dependency paths and the Windows notification preference live in config version 3 and are not job overrides.

Source audio filtering is deliberately not enabled in 0.2. Plans expose source track metadata, but the preservation rule is the product default. Any future filter must be opt-in, list kept/excluded tracks with reasons, and retain unknown metadata by default.
