# Contributing to PlexMuxy

Thank you for your interest in improving PlexMuxy! This guide explains how to set up a
development environment, build and debug the project, follow its coding and safety
conventions, and open a pull request.

PlexMuxy plans and builds Matroska (`.mkv`) files around Plex Media Server's scanning and
playback expectations. It matches external audio and ASS/SSA subtitles, attaches the fonts
those subtitles need, and writes track languages, names, flags, and metadata. The CLI and the
desktop GUI share the same planning/execution service, so most logic lives in one place.

## Requirements

- **Python 3.10–3.14** (the code targets `py310`; do not use syntax newer than 3.10).
- **[uv](https://docs.astral.sh/uv/)** for environment and dependency management (a plain
  `pip`/`venv` workflow also works, but `uv` is what CI and the docs assume).
- **[MKVToolNix](https://mkvtoolnix.download/)** — `mkvmerge` must be on `PATH`, or set
  `mkvmerge.path` in the config. PlexMuxy reads source tracks with `mkvmerge -J` and muxes
  with `mkvmerge`.
- **Windows GUI only:** the Microsoft Edge WebView2 runtime and, for installers,
  [Inno Setup](https://jrsoftware.org/isinfo.php) (`iscc` on `PATH`).
- **Integration tests only:** `ffmpeg` on `PATH` in addition to `mkvmerge`.

## Getting Started

```bash
# Clone your fork
git clone https://github.com/Masterain98/PlexMuxy.git
cd PlexMuxy

# Create a virtual environment with dev + GUI dependencies
uv sync --extra dev --extra gui

# Optional: add the build extra for standalone executables
uv sync --extra dev --extra gui --extra build
```

Run the tools directly from the working tree so your edits are picked up immediately:

```bash
uv run python -m plexmuxy show-config
uv run python -m plexmuxy plan D:\Media --json plan.json
uv run python -m plexmuxy_gui.app
```

After `uv sync`, the console scripts `plexmuxy` and `plexmuxy-gui` are also available inside
the environment (e.g. `uv run plexmuxy --help`).

## Build

Build the source distribution and wheel:

```bash
uv run --extra dev python -m build
```

Build standalone executables with PyInstaller (requires the `build` extra):

```bash
uv run --extra build python -m PyInstaller --clean --noconfirm plexmuxy-cli.spec
uv run --extra build python -m PyInstaller --clean --noconfirm plexmuxy-gui.spec
```

Build the Windows installer from the same single version source:

```powershell
pwsh scripts/build_installer.ps1
```

The installer version is forwarded from `plexmuxy/VERSION` to the Inno Setup script, so the
portable build, the installer, the wheel, and the CLI/GUI all share one version number.

## Commands

| Command | Description |
| --- | --- |
| `uv run --extra dev ruff check plexmuxy plexmuxy_gui tests` | Lint the codebase |
| `uv run --extra dev mypy plexmuxy plexmuxy_gui` | Static type checking |
| `uv run --extra dev pytest -m "not integration"` | Fast unit test suite |
| `uv run --extra dev pytest -m integration` | Real-media tests (needs `ffmpeg` + `mkvmerge`) |
| `uv run --extra dev python -m build` | Build sdist and wheel |
| `uv run python -m plexmuxy init-config` | Create the platform config |
| `uv run python -m plexmuxy show-config` | Print the active config |
| `uv run python -m plexmuxy migrate-config` | Migrate an older config in place |
| `uv run python -m plexmuxy plan MEDIA --json plan.json` | Read-only plan snapshot |
| `uv run python -m plexmuxy execute-plan plan.json` | Mux from an immutable plan |
| `uv run python -m plexmuxy diagnostics --output diagnostics.zip` | Export a redacted report |
| `uv run python -m plexmuxy_gui.app` | Launch the desktop GUI |

## Debugging

- **CLI:** launch the package module (`python -m plexmuxy ...`) instead of the installed
  entry point so source edits apply. Good breakpoint targets are `plexmuxy/cli.py` and
  `plexmuxy/service.py`. The shared planning/execution logic lives in `plexmuxy/service.py`.
- **GUI:** set `PLEXMUXY_GUI_DEBUG=1` before launching `plexmuxy_gui.app`. This enables debug
  logging and opens the pywebview/WebView2 developer tools.
  ```powershell
  # PowerShell
  $env:PLEXMUXY_GUI_DEBUG = "1"
  uv run --extra gui python -m plexmuxy_gui.app
  Remove-Item Env:PLEXMUXY_GUI_DEBUG
  ```
  ```bash
  # macOS / Linux
  PLEXMUXY_GUI_DEBUG=1 uv run --extra gui python -m plexmuxy_gui.app
  ```
  The Python/JS bridge is `plexmuxy_gui/api.py`; the frontend is `plexmuxy_gui/static/app.js`.
- **Logs:** runtime logs are written under the platform config directory —
  `%APPDATA%\PlexMuxy\logs` (Windows), `~/Library/Application Support/PlexMuxy/logs` (macOS),
  or `$XDG_CONFIG_HOME/plexmuxy/logs` (Linux).
- **Diagnostics:** `plexmuxy diagnostics --output diagnostics.zip` exports a redacted,
  media-free bundle useful for bug reports.
- **Inspecting tracks:** `mkvmerge -J <file>` shows the JSON track/container view that
  PlexMuxy itself parses; use it to confirm what PlexMuxy should see.

## Project Structure

| Path | Role |
| --- | --- |
| `plexmuxy/` | Core package: CLI (`cli.py`), planning/execution service (`service.py`), matching, fonts, config |
| `plexmuxy_gui/` | Desktop GUI (pywebview/WebView2). Python bridge `api.py`, frontend `static/app.js` |
| `tests/` | pytest suite (unit + `integration` marker; integration needs `ffmpeg` + `mkvmerge`) |
| `docs/` | Project docs (architecture, security, troubleshooting, releases, and the Matroska/mkvmerge references) |
| `scripts/` | Build/release helpers (incl. `build_installer.ps1` for Inno Setup) |
| `packaging/` | PyInstaller entry points, manifest, and the Inno Setup script |
| `*.spec` | PyInstaller specs for the CLI and GUI builds |
| `plexmuxy/VERSION` | **Single** version source for the whole project |
| `main.py`, `config.py`, `subtitle_utils.py`, `compressed.py` | Legacy compatibility entry/util modules |

## Code Conventions

- **Style & linting:** [Ruff](https://docs.astral.sh/ruff/) is the linter/formatter. The
  active rule set is `E, F, I, UP, B` with `E501` ignored and a line length of `120`. Run
  `ruff check` (and `ruff format` if you use it) before committing.
- **Typing:** [mypy](https://mypy-lang.org/) runs with `check_untyped_defs`,
  `warn_unused_ignores`, and `ignore_missing_imports` on Python 3.10. New code should carry
  type hints; avoid widening types just to satisfy the checker.
- **Naming:** `snake_case` for functions/variables, `PascalCase` for classes, `UPPER_CASE` for
  constants. Module and package names match the layout above.
- **Single version source:** the version lives only in `plexmuxy/VERSION` and is exposed via
  `plexmuxy.__version__`. Never hard-code a version string elsewhere; the release workflow
  reads this file.
- **Config is versioned:** config schemas have a version. Future/unrecognized config versions
  are **rejected**, not guessed — migrate with `migrate-config`. Never store secrets (e.g. a
  Plex token) in `config.json`; read them from an environment variable name configured by the
  user.
- **Internationalization:** human-readable CLI/GUI output may be localized with `--language`,
  but **JSON keys and error codes stay stable English** (e.g. `PLAN_STALE`). When you add
  user-facing strings, follow `LOCALIZATION.md` and keep the canonical keys English.
- **Dependencies:** runtime dependencies belong in `[project.dependencies]`; dev/GUI/build
  tooling belongs in the `dev`/`gui`/`build` extras in `pyproject.toml`. Don't add heavy or
  platform-specific imports to the core package without a hidden-import/exclude plan.
- **Documentation:** update `docs/` and `CHANGELOG.md` for user-facing changes. Matroska and
  `mkvmerge` specifics should reference the converted docs under `docs/mkvmerge/` and
  `docs/matroska-specs/` rather than web fetches.

## Safety Model (must preserve)

PlexMuxy handles user media, so a few invariants are non-negotiable:

- **Planning is read-only.** `plan` never modifies media; it only emits a reviewable JSON
  snapshot.
- **Execution is immutable and verified.** `execute-plan` consumes the exact snapshot and
  aborts with `PLAN_STALE` if any input, output, or configuration changed. Muxing writes to a
  temporary file and replaces the output **only after** `mkvmerge -J` confirms the container,
  tracks, flags, languages, names, and attachments.
- **Destructive actions are explicit.** `delete` cleanup requires `--yes`; overwrite requires
  opt-in. Failed partial output is renamed to `*.mkv.failed`, not deleted.
- When changing muxing logic, keep the verify-before-replace contract intact.

## Testing

- The suite lives in `tests/` and uses pytest. `testpaths` is already configured.
- **Fast suite:** `uv run --extra dev pytest -m "not integration"` — runs everywhere, no
  external binaries required.
- **Integration suite:** `uv run --extra dev pytest -m integration` — needs real `ffmpeg` and
  `mkvmerge` on `PATH`; it touches real media and is slower.
- **Coverage:** the quality gate requires branch coverage of at least **75%** for
  `plexmuxy` and `plexmuxy_gui`. Add or extend tests for any logic you change.
- Prefer small, deterministic unit tests for matching/font/metadata logic; reserve
  integration tests for end-to-end muxing behavior.

## Release & Versioning

- The **single version source** is the plain-text file `plexmuxy/VERSION`. To cut a release,
  bump that file; `plexmuxy.__version__`, setuptools, the CLI, diagnostics, and the GUI all
  read it.
- Release tags are `v<version>` (e.g. `v0.2.0`). The release workflow reads `plexmuxy/VERSION`
  and is triggered when that file changes on `main`.
- **Branch strategy:**
  - `main` is the protected, releasable branch.
  - `develop` is the integration branch for the next minor release.
  - Feature branches start from `develop`, stay short-lived, and merge through reviewed PRs.
  - Release candidates branch from `develop`, pass the full matrix and manual Windows
    acceptance, then merge to `main` and back to `develop`.
- PyPI publication uses Trusted Publishing and is a deliberate maintainer step after artifact
  and hash comparison.

## Pull Request Process

1. Fork the repository and create a branch from `develop` (features) or `main` (hotfixes).
2. Make your change following the conventions above; add or update tests and docs.
3. Run the local checks: `ruff check`, `mypy`, and `pytest -m "not integration"`.
4. Confirm a clean `python -m build` (and, for GUI work, the PyInstaller/installer build).
5. Open a pull request to `develop` (or `main` for fixes) with a clear description of the
   change and its motivation.

### Checklist

- [ ] Branch is based on `develop` (feature) or `main` (hotfix)
- [ ] `ruff check` passes with no new violations
- [ ] `mypy` passes on `plexmuxy` and `plexmuxy_gui`
- [ ] `pytest -m "not integration"` passes and coverage stays at/above 75%
- [ ] The safety model is preserved (no silent media mutation; verify-before-replace intact)
- [ ] User-facing changes update `docs/` and `CHANGELOG.md`
- [ ] New user-facing strings follow `LOCALIZATION.md`; JSON keys and error codes stay English
- [ ] No version string was hard-coded; `plexmuxy/VERSION` remains the only version source
- [ ] `python -m build` (and GUI/PyInstaller build when relevant) succeeds

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
