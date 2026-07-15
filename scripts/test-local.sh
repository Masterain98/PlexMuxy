#!/usr/bin/env sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
RUN_ROOT="$ROOT/.pytest-tmp/$$"
SYSTEM_TMP="$RUN_ROOT/system"
PYTEST_TMP="$RUN_ROOT/pytest"
CACHE_DIR="$RUN_ROOT/cache"
mkdir -p "$SYSTEM_TMP" "$PYTEST_TMP" "$CACHE_DIR"
TMPDIR="$SYSTEM_TMP" uv run --extra dev pytest -m "${PYTEST_MARKER:-not integration}" --basetemp "$PYTEST_TMP" -o "cache_dir=$CACHE_DIR" "$@"
