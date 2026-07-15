from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone

from plexmuxy.font_cache import FontSubsetCache, build_cache_key
from plexmuxy.font_catalog import build_font_catalog
from plexmuxy.font_subset import subset_font_face
from plexmuxy.models import FontCacheConfig
from tests.font_test_utils import build_test_ttf


def test_persistent_cache_hits_and_key_changes_with_characters_or_tool_contract(tmp_path):
    source = build_test_ttf(tmp_path / "source.ttf", family="Cache Test", characters=" ABC中")
    face = build_font_catalog([source]).faces[0]
    cache = FontSubsetCache(FontCacheConfig(), tmp_path / "cache")
    calls = 0

    def generator(destination):
        nonlocal calls
        calls += 1
        subset_font_face(face, source, {32, 65}, "PMX_CACHE", destination)

    first = cache.get_or_create(face, {32, 65}, "PMX_CACHE", generator)
    second = cache.get_or_create(face, {32, 65}, "PMX_CACHE", generator)
    changed_key, _ = build_cache_key(face, {32, 65, 66}, "PMX_CACHE")

    assert calls == 1
    assert first.hit is False
    assert second.hit is True
    assert first.path == second.path
    assert changed_key != first.key
    assert cache.stats().entries == 1


def test_corrupt_cache_entry_is_invalidated_and_rebuilt(tmp_path):
    source = build_test_ttf(tmp_path / "source.ttf", family="Cache Test", characters=" AB")
    face = build_font_catalog([source]).faces[0]
    cache = FontSubsetCache(FontCacheConfig(), tmp_path / "cache")
    calls = 0

    def generator(destination):
        nonlocal calls
        calls += 1
        subset_font_face(face, source, {32, 65}, "PMX_CACHE", destination)

    first = cache.get_or_create(face, {32, 65}, "PMX_CACHE", generator)
    first.path.write_bytes(b"corrupt")
    rebuilt = cache.get_or_create(face, {32, 65}, "PMX_CACHE", generator)

    assert calls == 2
    assert rebuilt.hit is False
    assert rebuilt.path.read_bytes() != b"corrupt"


def test_key_lock_prevents_concurrent_half_entries(tmp_path):
    source = build_test_ttf(tmp_path / "source.ttf", family="Cache Test", characters=" AB")
    face = build_font_catalog([source]).faces[0]
    cache = FontSubsetCache(FontCacheConfig(), tmp_path / "cache")
    calls = 0
    barrier = threading.Barrier(2)
    results = []

    def worker():
        nonlocal calls
        barrier.wait()

        def generator(destination):
            nonlocal calls
            calls += 1
            subset_font_face(face, source, {32, 65}, "PMX_CACHE", destination)

        results.append(cache.get_or_create(face, {32, 65}, "PMX_CACHE", generator))

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert calls == 1
    assert len(results) == 2
    assert {result.path for result in results} == {results[0].path}
    assert not list((tmp_path / "cache").glob("*.lock"))
    assert not list((tmp_path / "cache").glob(".*.tmp-*"))


def test_cache_prunes_old_entries_and_clear_reports_stats(tmp_path):
    source = build_test_ttf(tmp_path / "source.ttf", family="Cache Test", characters=" AB")
    face = build_font_catalog([source]).faces[0]
    cache = FontSubsetCache(FontCacheConfig(max_age_days=1), tmp_path / "cache")
    entry = cache.get_or_create(
        face,
        {32, 65},
        "PMX_CACHE",
        lambda destination: subset_font_face(face, source, {32, 65}, "PMX_CACHE", destination),
    )
    metadata_path = entry.path.parent / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["last_accessed"] = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    assert cache.prune().entries == 0
    assert cache.clear().size_bytes == 0
