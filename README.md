<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="./logo/svg/plexmuxy-lockup-dark.svg" />
    <source media="(prefers-color-scheme: light)" srcset="./logo/svg/plexmuxy-lockup-light.svg" />
    <img src="./logo/svg/plexmuxy-lockup-light.svg" width="640" alt="PlexMuxy" />
  </picture>
</p>

# PlexMuxy

PlexMuxy plans and builds Matroska files around Plex Media Server's scanning, playback, and metadata expectations. It matches external audio and ASS/SSA subtitles, attaches the fonts those subtitles need, and writes track languages, names, flags, and other metadata so Plex can discover and present the added content correctly. Subtitle tracks can expose both language and release-group information instead of appearing as unnamed tracks. The CLI and desktop GUI use the same planning and execution service.

## Safety model

- Planning never changes media files. Save a reviewable snapshot with `plexmuxy plan MEDIA --json plan.json`.
- Execution uses that exact snapshot and stops with `PLAN_STALE` if an input, output, or configuration changed.
- Muxing writes to a temporary file. The final output is replaced only after `mkvmerge -J` confirms the container, video/subtitle tracks, flags, languages, names, and attachments.
- Cleanup runs only for successful, verified outputs. A shared input is retained unless every dependent plan succeeds.
- Delete cleanup requires `--yes`; overwrite also requires explicit opt-in. Failed partial output is renamed to `*.mkv.failed` by default.

## Install

PlexMuxy requires Python 3.10–3.14 and [MKVToolNix](https://mkvtoolnix.download/). Ensure `mkvmerge` is on `PATH`, or set `mkvmerge.path` in the config.

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
Releases also include a per-user Windows installer with a stable application identity, Start-menu entry, uninstaller, and notification activation. The portable ZIP remains supported.

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

# Human-readable CLI language; JSON keys and error codes remain English/stable
plexmuxy --language zh-CN show-config
plexmuxy --output-format json plan D:\Media

# Explicit update check (disabled by default)
plexmuxy check-updates --force
```

Useful job overrides include `--output-dir`, `--output-suffix`, `--name-strategy`, `--name-template`, `--extra-dir`, `--font-mode`, `--overwrite`, and `--cleanup`. For example, `--font-mode subset` enables font subsetting for that plan.

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

Source-audio filtering, update checks, and Plex refreshes are disabled by default. Plex tokens are read from the configured environment-variable name (default `PLEXMUXY_PLEX_TOKEN`), never stored in `config.json`; local-to-server path mappings are required before a refresh request is sent. Persistent font subsets use a validated, quota-limited local cache that can be disabled or cleared from the Environment view.

The desktop “Environment configuration” view is persistent and separate from job options. Each dependency shows its verified executable, discovery source, and version. “Auto-detect” performs a fresh probe and keeps the result as an unsaved draft; it never replaces an explicit saved path silently. Windows also discovers MKVToolNix through 32/64-bit HKLM/HKCU uninstall information. The UnRAR action downloads only RARLAB's signed x64 installer over allowlisted HTTPS, lets the official installer handle setup, and offers the detected executable for confirmation before saving. Windows builds opt into Per-Monitor V2 awareness before creating native windows so the WebView and file dialogs follow system scaling on high-DPI and mixed-monitor setups.

Windows job notifications can be enabled on that page. The current native Windows Shell backend covers completed, failed, and cancelled jobs, and notification failures never change a mux result. Action buttons, application activation, and durable notification-center identity require a future installer/application-identity integration with the Windows App SDK.

## Matching

Each subtitle or external audio file is assigned once using this priority: exact stem (1.0), normalized title (0.85), normalized episode identity (0.70), and optional controlled single-video movie fallback. Episode parsing supports `[1]`, `[100]`, `S01E01`, `S01EP01`, `E01`, `EP01`, `.01.`, `SP01`, `Special`, and `OVA`.

Equal best candidates become `ambiguous_match` and are skipped. Low-confidence candidates become `unmatched`. The GUI and CLI display these reasons; PlexMuxy never chooses by filename ordering.

## Supported file types

PlexMuxy reads the following source formats and always writes a Matroska (`.mkv`) output:

| Role | Extensions (default) |
| --- | --- |
| Video containers | `.mkv`, `.mp4`, `.avi`, `.flv` |
| External subtitles | `.ass`, `.ssa` |
| External audio | `.mka` |
| Font attachments | `.ttf`, `.otf`, `.ttc`, `.otc` |
| Font archives | `.zip`, `.7z`, `.rar` |

The video-container list is configurable in `config.json` under `media.video_extensions` (and the other `media.*_extensions` lists), so additional containers that `mkvmerge` can demux can be enabled. Output is always Matroska, which is what Plex expects.

For the scenario from issue #14: PlexMuxy already muxes an `.avi` video with an `.ssa` subtitle into a single `.mkv`. See [Commands](#commands) and [Configuration](#configuration) for the `--output-dir`, `--name-strategy`, and `--cleanup` job overrides that control where the output lands and how it is named.

## Fonts and source tracks

`font.mode=all` preserves the compatibility-first behavior. `referenced` uses the structural ASS/SSA parser and internal font names to select complete fonts. `subset` performs real glyph subsetting: it follows dynamic `Format` fields plus Style and override state (`\fn`, `\r`, `\b`, `\i`, `\p`, and `\t(...)`), enumerates every TTF/OTF/TTC/OTC face, and deterministically matches internal family, weight, italic, and cmap metadata. Temporary subtitles rewrite only validated families to `PMX_<hash>` aliases; source subtitles and fonts are never modified.

Every plan in a batch is prepared and revalidated in an execution-scoped workspace before any `mkvmerge` process starts. Identical subset work is cached for that execution and the workspace is removed after success, failure, or cancellation. If FontTools cannot safely subset a matched family, the default policy attaches that family’s complete source faces without rewriting its name. Missing or ambiguous fonts, missing glyphs, structurally unsafe ASS, and ambiguous BOM-less GB18030/CP932 input are never silently treated as safe subsets. Configure `missing_font_action` and `subset_failure_action` for the permitted skip, fail-job, or full-font behavior.

Output verification checks the expected attachment file names and MIME types as well as track properties and counts.

Source container tracks are read with `mkvmerge -J` and shown in plans. The 0.2 product decision is to preserve all source tracks. Filter configuration is reserved for explicit future use; unknown languages and untitled tracks must remain included.

## Development

Create a local environment with the development and GUI dependencies:

```bash
uv sync --extra dev --extra gui
```

### Debug the CLI from source

Run the package module so edits are picked up directly from the working tree:

```bash
uv run python -m plexmuxy show-config
uv run python -m plexmuxy plan D:\Media --json plan.json
```

For an IDE debugger, select `.venv/Scripts/python.exe` on Windows or `.venv/bin/python` on macOS/Linux, launch the `plexmuxy` module, and put the desired CLI arguments in the debugger configuration. Useful breakpoint entry points are `plexmuxy/cli.py` and `plexmuxy/service.py`.

### Debug the GUI from source

`PLEXMUXY_GUI_DEBUG=1` enables debug logging and pywebview/WebView2 developer mode:

```powershell
# PowerShell
$env:PLEXMUXY_GUI_DEBUG = "1"
uv run --extra gui python -m plexmuxy_gui.app
Remove-Item Env:PLEXMUXY_GUI_DEBUG
```

```bash
# macOS/Linux
PLEXMUXY_GUI_DEBUG=1 uv run --extra gui python -m plexmuxy_gui.app
```

For an IDE debugger, launch the `plexmuxy_gui.app` module with the same environment variable. The Python bridge lives in `plexmuxy_gui/api.py`, the shared execution path in `plexmuxy/service.py`, and the frontend in `plexmuxy_gui/static/app.js`. GUI logs are written under the platform config directory: `%APPDATA%\PlexMuxy\logs` on Windows, `~/Library/Application Support/PlexMuxy/logs` on macOS, or `$XDG_CONFIG_HOME/plexmuxy/logs` on Linux.

### Validate and build

```bash
uv run --extra dev pytest -m "not integration"
uv run --extra dev pytest -m integration       # requires ffmpeg + mkvmerge
uv run --extra dev ruff check plexmuxy plexmuxy_gui tests
uv run --extra dev mypy plexmuxy plexmuxy_gui
uv run --extra dev python -m build

# Install the build extra before creating standalone executables.
uv sync --extra dev --extra gui --extra build
uv run --extra build python -m PyInstaller --clean --noconfirm plexmuxy-cli.spec
uv run --extra build python -m PyInstaller --clean --noconfirm plexmuxy-gui.spec
```

See [architecture](docs/architecture.md), [troubleshooting](docs/troubleshooting.md), [security](docs/security.md), and [release process](docs/release-process.md).

## License

MIT
