# PlexMuxy

PlexMuxy safely batches video, external audio, ASS/SSA subtitles, and font attachments into Matroska files for Plex. The CLI and desktop GUI use the same planning and execution service.

## Safety model

- Planning never changes media files. Save a reviewable snapshot with `plexmuxy plan MEDIA --json plan.json`.
- Execution uses that exact snapshot and stops with `PLAN_STALE` if an input, output, or configuration changed.
- Muxing writes to a temporary file. The final output is replaced only after `mkvmerge -J` confirms the container, video/subtitle tracks, flags, languages, names, and attachments.
- Cleanup runs only for successful, verified outputs. A shared input is retained unless every dependent plan succeeds.
- Delete cleanup requires `--yes`; overwrite also requires explicit opt-in. Failed partial output is renamed to `*.mkv.failed` by default.

## Install

PlexMuxy requires Python 3.10–3.13 and [MKVToolNix](https://mkvtoolnix.download/). Ensure `mkvmerge` is on `PATH`, or set `mkvmerge.path` in the config.

```bash
pip install plexmuxy
plexmuxy --help
```

Desktop GUI:

```bash
pip install "plexmuxy[gui]"
plexmuxy gui
# or: plexmuxy-gui
```

The Windows GUI uses the Microsoft Edge WebView2 Evergreen Runtime. Windows 11 normally includes it; Windows 10 may require the [WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/). The standalone releases use the same Evergreen dependency to keep downloads small.

Windows release archives contain independent CLI and GUI builds and do not require a local Python installation. Verify downloads against `SHA256SUMS.txt`.

## Commands

```bash
# Create and inspect the platform config
plexmuxy init-config
plexmuxy show-config

# Migrate in place (creates config.json.bak-YYYYMMDD-HHMMSS)
plexmuxy migrate-config
plexmuxy migrate-config --source old.json --target new.json

# Preview, save, and execute an immutable plan
plexmuxy plan D:\Media --json plan.json
plexmuxy execute-plan plan.json

# One-shot plan and mux; cleanup is explicitly disabled here
plexmuxy mux D:\Media --cleanup none

# Destructive cleanup requires confirmation
plexmuxy mux D:\Media --cleanup delete --yes

# Export a redacted report with no media content
plexmuxy diagnostics --output diagnostics.zip
```

Useful job overrides include `--output-dir`, `--output-suffix`, `--name-strategy`, `--name-template`, `--extra-dir`, `--overwrite`, and `--cleanup`.

## Configuration

The default config lives in `%APPDATA%\PlexMuxy\config.json` (Windows), `~/Library/Application Support/PlexMuxy/config.json` (macOS), or `$XDG_CONFIG_HOME/plexmuxy/config.json` (Linux). Future config versions are rejected rather than guessed. Legacy configuration remains importable in 0.2, emits deprecation guidance through legacy entry points, and should be migrated before 0.3.

Important defaults:

```json
{
  "matching": {
    "movie_fallback": false,
    "allow_episode_only_match": true,
    "minimum_confidence": 0.7,
    "ambiguous_action": "skip"
  },
  "task": {
    "cleanup": "move",
    "overwrite": false,
    "failed_output_action": "rename"
  },
  "font": {
    "mode": "all",
    "missing_font_action": "warn"
  },
  "concurrency": {
    "max_parallel_mux_jobs": 1
  }
}
```

Parallel mux jobs are intentionally limited to 1–4 and default to 1. The old `thread_count` key is accepted only for migration. Archive limits apply before ZIP/7z extraction; uninspectable RAR archives require explicit permission.

## Matching

Each subtitle or external audio file is assigned once using this priority: exact stem (1.0), normalized title (0.85), normalized episode identity (0.70), and optional controlled single-video movie fallback. Episode parsing supports `[1]`, `[100]`, `S01E01`, `S01EP01`, `E01`, `EP01`, `.01.`, `SP01`, `Special`, and `OVA`.

Equal best candidates become `ambiguous_match` and are skipped. Low-confidence candidates become `unmatched`. The GUI and CLI display these reasons; PlexMuxy never chooses by filename ordering.

## Fonts and source tracks

`font.mode=all` preserves the compatibility-first behavior. `referenced` parses ASS/SSA style font names and `\fn` overrides, matches font metadata, and follows `missing_font_action`. `subset` currently falls back to referenced full fonts and reports that decision; it never emits a knowingly incomplete subset.

Source container tracks are read with `mkvmerge -J` and shown in plans. The 0.2 product decision is to preserve all source tracks. Filter configuration is reserved for explicit future use; unknown languages and untitled tracks must remain included.

## Development

```bash
pip install -e ".[dev,build]"
pytest -m "not integration"
pytest -m integration       # requires ffmpeg + mkvmerge
ruff check plexmuxy plexmuxy_gui tests
mypy plexmuxy plexmuxy_gui
python -m build
python -m PyInstaller --clean --noconfirm plexmuxy-cli.spec
python -m PyInstaller --clean --noconfirm plexmuxy-gui.spec
```

See [architecture](docs/architecture.md), [troubleshooting](docs/troubleshooting.md), [security](docs/security.md), and [release process](docs/release-process.md).

## License

MIT
