# Performance baseline

PlexMuxy keeps directory-level mux concurrency at one by default. Do not raise it from anecdotal observations.

Run the planning benchmark against representative 10, 50, and 100-video fixtures:

```powershell
uv run python scripts/benchmark.py D:\Fixtures\PlexMuxy-10 --iterations 5 --output benchmarks/plan-10.json
uv run python scripts/benchmark.py D:\Fixtures\PlexMuxy-50 --iterations 5 --output benchmarks/plan-50.json
uv run python scripts/benchmark.py D:\Fixtures\PlexMuxy-100 --iterations 5 --output benchmarks/plan-100.json
```

The JSON records plan duration, Python peak memory, video/subtitle/audio/attachment counts, phase timestamps, and current font-cache size. The benchmark calls `build_job_plan` only: it never starts mkvmerge or cleanup.

For release profiling, record the same machine, storage, ffmpeg/MKVToolNix/FontTools versions, input counts, archive sizes, cold/warm cache state, mux duration, peak process memory, and temporary disk high-water mark. Compare a cold subset run with a warm run; accept the cache only when outputs still pass digest and font validation and the warm result is measurably faster. Store machine-specific results outside the repository unless the fixture is redistributable.

The cache key includes the source digest, archive member, face index, requested codepoint ranges, alias, output format, table profile, analyzer/subset schema, and FontTools version. Therefore a faster warm run never relaxes correctness checks.
