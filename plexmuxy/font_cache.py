from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import fontTools

from .font_subset import SUBSET_PROFILE_VERSION, FontSubsetError, output_extension, validate_subset_font
from .models import FontCacheConfig, FontFaceRef

CACHE_SCHEMA_VERSION = 1
TABLE_PROFILE = "fonttools-default-layout-all-v1"
ANALYZER_VERSION = 1


class FontCacheError(RuntimeError):
    pass


@dataclass(frozen=True)
class FontCacheEntry:
    key: str
    path: Path
    checksum: str
    size: int
    hit: bool


@dataclass(frozen=True)
class FontCacheStats:
    path: str
    entries: int
    size_bytes: int
    max_size_bytes: int


def platform_font_cache_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "PlexMuxy" / "subsets" / f"v{CACHE_SCHEMA_VERSION}"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "PlexMuxy" / "subsets" / f"v{CACHE_SCHEMA_VERSION}"
    base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "plexmuxy" / "subsets" / f"v{CACHE_SCHEMA_VERSION}"


def cache_key_material(
    face: FontFaceRef,
    codepoints: set[int],
    alias_family: str,
) -> dict:
    return {
        "cache_schema_version": CACHE_SCHEMA_VERSION,
        "font_source_sha256": face.source_digest,
        "archive_sha256": face.archive_digest,
        "archive_member": face.archive_member,
        "face_index": face.face_index,
        "outline_type": face.outline_type,
        "variable_font": face.is_variable,
        "variable_instance": None,
        "codepoint_ranges": [list(item) for item in _compress_codepoints(codepoints)],
        "alias_family": alias_family,
        "fonttools_version": fontTools.__version__,
        "harfbuzz_version": None,
        "subset_profile_version": SUBSET_PROFILE_VERSION,
        "analyzer_version": ANALYZER_VERSION,
        "table_profile": TABLE_PROFILE,
        "output_format": output_extension(face),
    }


def build_cache_key(face: FontFaceRef, codepoints: set[int], alias_family: str) -> tuple[str, dict]:
    material = cache_key_material(face, codepoints, alias_family)
    canonical = json.dumps(material, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("ascii")).hexdigest(), material


class FontSubsetCache:
    def __init__(self, config: FontCacheConfig, root: Path | None = None) -> None:
        self.config = config
        self.root = Path(root or platform_font_cache_path()).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def get_or_create(
        self,
        face: FontFaceRef,
        codepoints: set[int],
        alias_family: str,
        generator: Callable[[Path], object],
    ) -> FontCacheEntry:
        key, material = build_cache_key(face, codepoints, alias_family)
        entry_dir = self.root / key
        cached = self._load_valid(entry_dir, key, material, face, codepoints, alias_family)
        if cached is not None:
            return cached
        lock = self.root / f"{key}.lock"
        self._acquire_lock(lock)
        try:
            cached = self._load_valid(entry_dir, key, material, face, codepoints, alias_family)
            if cached is not None:
                return cached
            if entry_dir.exists():
                self._retire_directory(entry_dir)
            temp_dir = self.root / f".{key}.tmp-{uuid.uuid4().hex}"
            temp_dir.mkdir()
            extension = output_extension(face)
            font_path = temp_dir / f"font{extension}"
            try:
                generator(font_path)
                validate_subset_font(font_path, face, alias_family, codepoints)
                checksum = _sha256(font_path)
                now = datetime.now(timezone.utc).isoformat()
                metadata = {
                    **material,
                    "key": key,
                    "font_file": font_path.name,
                    "checksum": checksum,
                    "created_at": now,
                    "last_accessed": now,
                }
                _write_json(temp_dir / "metadata.json", metadata)
                self._publish_directory(temp_dir, entry_dir)
            except Exception:
                shutil.rmtree(temp_dir, ignore_errors=True)
                raise
            cached_path = entry_dir / font_path.name
            result = FontCacheEntry(key, cached_path, checksum, cached_path.stat().st_size, False)
        finally:
            lock.unlink(missing_ok=True)
        self.prune()
        return result

    def _load_valid(
        self,
        entry_dir: Path,
        key: str,
        material: dict,
        face: FontFaceRef,
        codepoints: set[int],
        alias_family: str,
    ) -> FontCacheEntry | None:
        metadata_path = entry_dir / "metadata.json"
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            for field, expected in material.items():
                if metadata.get(field) != expected:
                    return None
            font_name = metadata["font_file"]
            if not isinstance(font_name, str) or Path(font_name).name != font_name:
                return None
            font_path = entry_dir / font_name
            checksum = metadata["checksum"]
            if not font_path.is_file() or _sha256(font_path) != checksum:
                return None
            validate_subset_font(font_path, face, alias_family, codepoints)
            metadata["last_accessed"] = datetime.now(timezone.utc).isoformat()
            _write_json(metadata_path, metadata)
            return FontCacheEntry(key, font_path, checksum, font_path.stat().st_size, True)
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError, FontSubsetError):
            return None

    def _retire_directory(self, entry_dir: Path) -> None:
        """Remove a bad entry from the live namespace before best-effort cleanup."""
        retired = self.root / f".{entry_dir.name}.stale-{uuid.uuid4().hex}"
        try:
            os.replace(entry_dir, retired)
        except OSError as exc:
            for _attempt in range(3):
                shutil.rmtree(entry_dir, ignore_errors=True)
                if not entry_dir.exists():
                    return
                time.sleep(0.02)
            raise FontCacheError(f"Could not invalidate font cache entry: {entry_dir.name}") from exc
        shutil.rmtree(retired, ignore_errors=True)

    @staticmethod
    def _publish_directory(temp_dir: Path, entry_dir: Path) -> None:
        """Atomically publish after transient Windows scanner locks are released."""
        last_error: OSError | None = None
        for attempt in range(8):
            try:
                os.replace(temp_dir, entry_dir)
                return
            except PermissionError as exc:
                last_error = exc
                time.sleep(0.02 * (attempt + 1))
        raise FontCacheError(f"Could not publish font cache entry: {entry_dir.name}") from last_error

    def _acquire_lock(self, lock: Path, timeout: float = 30) -> None:
        deadline = time.monotonic() + timeout
        while True:
            try:
                descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(descriptor)
                return
            except FileExistsError:
                try:
                    if time.time() - lock.stat().st_mtime > 600:
                        lock.unlink(missing_ok=True)
                        continue
                except OSError:
                    pass
                if time.monotonic() >= deadline:
                    raise FontCacheError(f"Timed out waiting for font cache key: {lock.stem}") from None
                time.sleep(0.05)

    def stats(self) -> FontCacheStats:
        entries = 0
        size = 0
        for item in self.root.iterdir():
            if not item.is_dir() or item.name.startswith("."):
                continue
            entries += 1
            size += sum(path.stat().st_size for path in item.rglob("*") if path.is_file())
        return FontCacheStats(str(self.root), entries, size, self.config.max_size_mb * 1024 * 1024)

    def clear(self) -> FontCacheStats:
        for item in self.root.iterdir():
            if item.is_dir() and not item.name.startswith(".") and not (self.root / f"{item.name}.lock").exists():
                shutil.rmtree(item, ignore_errors=True)
        return self.stats()

    def prune(self) -> FontCacheStats:
        now = datetime.now(timezone.utc)
        candidates: list[tuple[float, Path, int]] = []
        total = 0
        for item in self.root.iterdir():
            if not item.is_dir() or item.name.startswith(".") or (self.root / f"{item.name}.lock").exists():
                continue
            try:
                metadata = json.loads((item / "metadata.json").read_text(encoding="utf-8"))
                accessed = datetime.fromisoformat(metadata["last_accessed"])
                size = sum(path.stat().st_size for path in item.rglob("*") if path.is_file())
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                shutil.rmtree(item, ignore_errors=True)
                continue
            age_days = (now - accessed).total_seconds() / 86400
            if age_days > self.config.max_age_days:
                shutil.rmtree(item, ignore_errors=True)
                continue
            timestamp = accessed.timestamp()
            candidates.append((timestamp, item, size))
            total += size
        maximum = self.config.max_size_mb * 1024 * 1024
        for _accessed, item, size in sorted(candidates):
            if total <= maximum:
                break
            shutil.rmtree(item, ignore_errors=True)
            total -= size
        return self.stats()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: dict) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _compress_codepoints(codepoints: set[int]) -> tuple[tuple[int, int], ...]:
    values = sorted(codepoints)
    if not values:
        return ()
    result: list[tuple[int, int]] = []
    start = previous = values[0]
    for value in values[1:]:
        if value == previous + 1:
            previous = value
            continue
        result.append((start, previous))
        start = previous = value
    result.append((start, previous))
    return tuple(result)
