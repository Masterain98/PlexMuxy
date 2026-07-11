# Architecture

```text
CLI / GUI
    ↓
Service (plan snapshot, progress, cancellation, bounded concurrency)
    ↓
Scanner → Matcher → Planner
    ↓                 ↓
Archive/font safety   Source-track inspection
    ↓
Mux subprocess → Structural verifier → Batch cleanup
```

The adapters validate user payloads and call `plexmuxy.service`; they do not implement mux policy. `scanner` classifies files without following symlinks or hidden paths by default. `matcher` globally assigns each candidate so a file cannot silently attach to two videos. `planner` creates deterministic outputs, tracks, attachment intent, and cleanup candidates.

`snapshot` records the normalized config plus size and nanosecond modification time for every existing input. Execution validates it and rechecks output appearance. Deserialization requires absolute paths and reconstructs typed models; output paths are recomputed from the saved configuration to reject edited plan paths.

`muxer` owns the `mkvmerge` subprocess so cancellation can terminate it. It never writes directly to the final pathname. `verify_mux_output` parses `mkvmerge -J`, distinguishes execution and verification error codes, and verifies expected structure. `cleanup` operates once, after all jobs settle, using dependency groups for shared files.

The GUI `PlexMuxyApi` starts daemon-backed jobs and exposes `start_job`, `get_job_status`, `get_job_report`, and `cancel_job`. Progress events are plain core objects; the core package has no GUI dependency.

Source audio filtering is deliberately not enabled in 0.2. Plans expose source track metadata, but the preservation rule is the product default. Any future filter must be opt-in, list kept/excluded tracks with reasons, and retain unknown metadata by default.
