from __future__ import annotations

import argparse
import json
import statistics
import time
import tracemalloc
from pathlib import Path

from plexmuxy.config import load_config
from plexmuxy.service import build_job_plan


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure PlexMuxy planning without changing media files.")
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    config = load_config(args.config, create_if_missing=False) if args.config else load_config()
    samples = []
    for _index in range(max(1, args.iterations)):
        phases = []
        start = time.perf_counter()
        tracemalloc.start()
        report = build_job_plan(
            args.input_dir,
            config,
            progress_callback=lambda event, target=phases: target.append((event.phase, time.perf_counter())),
        )
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        if report.error:
            raise SystemExit(f"[{report.error_code}] {report.error}")
        samples.append({
            "duration_ms": round((time.perf_counter() - start) * 1000, 2),
            "peak_python_memory_bytes": peak,
            "plan_count": len(report.plans),
            "subtitle_count": sum(len(plan.subtitle_tracks) for plan in report.plans),
            "audio_count": sum(len(plan.audio_tracks) for plan in report.plans),
            "attachment_count": sum(len(plan.attachments) for plan in report.plans),
            "phase_timestamps_ms": [
                {"phase": phase, "elapsed_ms": round((stamp - start) * 1000, 2)} for phase, stamp in phases
            ],
        })
    payload = {
        "schema_version": 1,
        "input_dir": str(args.input_dir.expanduser().resolve()),
        "iterations": len(samples),
        "median_duration_ms": round(statistics.median(item["duration_ms"] for item in samples), 2),
        "samples": samples,
        "notes": "Planning-only benchmark; no mux subprocess or cleanup is executed.",
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
