# AGENT.md — PlexMuxy

Guidance for AI agents working in this repository. PlexMuxy is a Python tool that
**plans and builds Matroska (`.mkv`) files** tuned for Plex Media Server: it matches
external audio and ASS/SSA subtitles, attaches the fonts those subtitles need, and
writes track languages, names, flags, and metadata. The CLI and desktop GUI share the
same planning/execution service. Matroska container semantics and the `mkvmerge`
command-line tool are central to everything here — see [Documentation index](#documentation-index)
for the spec references.

## Tech & key dependencies
- **Language:** Python 3.10–3.14. Packaging/build via `uv` + `PyInstaller`; Windows GUI on WebView2.
- **External binary:** [MKVToolNix](https://mkvtoolnix.download/) — `mkvmerge` must be on `PATH`
  (or set `mkvmerge.path` in config). PlexMuxy reads source tracks with `mkvmerge -J` and
  performs the actual muxing with `mkvmerge`.
- **Container format:** Matroska (`*.mkv`) — output is *always* Matroska.
- **Subtitles:** ASS/SSA parsing (structural), font subsetting via FontTools.

## Repository layout
| Path | Role |
|------|------|
| `plexmuxy/` | Core package: CLI (`cli.py`), planning/execution service (`service.py`), matching, fonts, config |
| `plexmuxy_gui/` | Desktop GUI (pywebview/WebView2). Python bridge `api.py`, frontend `static/app.js` |
| `tests/` | pytest suite (unit + `integration` marker; integration needs ffmpeg + mkvmerge) |
| `docs/` | Project docs (architecture, security, troubleshooting, releases, **mkvmerge**, **matroska-specs**) |
| `scripts/` | Build/release helpers (incl. `build_installer.ps1` for Inno Setup) |
| `main.py`, `subtitle_utils.py`, `compressed.py`, `config.py` | Top-level entry/util modules |

## Common agent tasks
```bash
uv sync --extra dev --extra gui                 # set up env
uv run python -m plexmuxy plan D:\Media --json plan.json   # plan (read-only)
uv run python -m plexmuxy execute-plan plan.json          # execute immutable plan
uv run --extra dev pytest -m "not integration"           # tests
uv run --extra dev ruff check plexmuxy plexmuxy_gui tests # lint
uv run --extra dev mypy plexmuxy plexmuxy_gui             # type-check
uv run --extra dev python -m build                        # build sdist/wheel
```
- **Debug entry points:** `plexmuxy/cli.py`, `plexmuxy/service.py`; GUI bridge `plexmuxy_gui/api.py`.
- **GUI debug mode:** set `PLEXMUXY_GUI_DEBUG=1` before launching `plexmuxy_gui.app`.

## Safety model (important)
- Planning (`plan`) is **read-only**; it never changes media. It emits a reviewable JSON snapshot.
- Execution (`execute-plan`) consumes that exact snapshot and aborts with `PLAN_STALE` if any
  input/output/config changed. Muxing writes to a temp file, replaces output only after
  `mkvmerge -J` verifies container/tracks/flags/languages/names/attachments.
- Destructive cleanup (`delete`) requires `--yes`; failed partial output is renamed `*.mkv.failed`.
- When editing muxing logic, preserve the verify-before-replace contract.

## Documentation index

The two spec directories below were **auto-converted from the official sources** into
agent-friendly Markdown (option tables, fenced code/diagram blocks, absolutized links).
Each file carries a `> Source:` banner noting its origin. Prefer these over web fetches
when you need Matroska/mkvmerge details during a task.

### `docs/mkvmerge/`
| File | Contents |
|------|----------|
| [`v100.md`](docs/mkvmerge/v100.md) | **mkvmerge command-line reference (v100).** All 21 sections, ~126 options as `| Option | Description |` tables, synopsis, and usage/examples. Use this to confirm exact flag names, parameters, and split/link/append behavior. |

### `docs/matroska-specs/`
| File | Contents |
|------|----------|
| [`diagram.md`](docs/matroska-specs/diagram.md) | Matroska/EBML **file structure & element layout** (EBML Header, Segment, Top-Level Elements) with ASCII diagrams. |
| [`attachments.md`](docs/matroska-specs/attachments.md) | How **attachments** (fonts, cover art, etc.) work in Matroska and their constraints. |
| [`tagging.md`](docs/matroska-specs/tagging.md) | The **tagging system**: `SimpleTag`, `Targets`, `TargetType`/`TargetTypeValue`, nesting rules, and the full tag tables. |
| [`ordering.md`](docs/matroska-specs/ordering.md) | Element/stream **ordering** rules within a Matroska file. |
| [`tagging-audio-example.md`](docs/matroska-specs/tagging-audio-example.md) | Worked **audio tagging** XML examples (nested tag trees for albums/tracks). |
| [`tagging-video-example.md`](docs/matroska-specs/tagging-video-example.md) | Worked **video tagging** XML examples. |
| [`tags-precedence.md`](docs/matroska-specs/tags-precedence.md) | **Tag precedence** rules when multiple tags apply. |
| [`matroska-implement.md`](docs/matroska-specs/matroska-implement.md) | Matroska **implementation guidelines / notes.** |

### Other project docs (in `docs/`)
`architecture.md`, `security.md`, `troubleshooting.md`, `release-process.md`,
`branch-strategy.md`, `font-rendering.md`, `performance-baseline.md`, `roadmap.md`,
and `releases/`. These describe PlexMuxy internals (not the external specs).

## Conventions
- Output is always Matroska; track/language/name/flag metadata follows Plex expectations.
- Config is versioned; future config versions are **rejected**, not guessed. Migrate via
  `migrate-config`. CLI JSON keys and error codes are stable English even when `--language`
  localizes human-readable output.
- License: MIT.
