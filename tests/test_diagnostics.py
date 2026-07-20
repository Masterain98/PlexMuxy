"""Tests for the diagnostic payload, focused on the media/project root."""

import sys
from pathlib import Path

import pytest

from plexmuxy.config import AppConfig
from plexmuxy.diagnostics import (
    collect_diagnostic_payload,
    format_diagnostic_payload,
)

pytestmark = pytest.mark.skipif(
    sys.version_info < (3, 10), reason="requires Python 3.10+ (PEP 604 unions)"
)


def _job_context(root: Path) -> dict:
    return {
        "job": {"id": "job-1", "input_dir": str(root), "state": "completed"},
        "events": [],
        "report": {"input_dir": str(root), "plans": [], "results": {}},
    }


def test_media_root_present_in_job_diagnostics(tmp_path: Path):
    payload = collect_diagnostic_payload(AppConfig(), _job_context(tmp_path))
    assert payload["media_root"] == str(tmp_path.resolve())
    assert "<PATH>" not in payload["media_root"]


def test_media_root_absent_without_job_context():
    payload = collect_diagnostic_payload(AppConfig())
    assert "media_root" not in payload


def test_job_context_still_redacted_but_media_root_full(tmp_path: Path):
    payload = collect_diagnostic_payload(AppConfig(), _job_context(tmp_path))
    # The job context itself stays redacted for privacy...
    assert "<PATH>" in payload["job"]["report"]["input_dir"]
    # ...while the dedicated field keeps the usable location.
    assert payload["media_root"] == str(tmp_path.resolve())


def test_media_root_prefers_report_over_job(tmp_path: Path):
    other = tmp_path / "other"
    payload = collect_diagnostic_payload(
        AppConfig(),
        {
            "job": {"input_dir": str(other), "state": "completed"},
            "events": [],
            "report": {"input_dir": str(tmp_path), "plans": []},
        },
    )
    assert payload["media_root"] == str(tmp_path.resolve())


def test_media_root_in_text_output(tmp_path: Path):
    payload = collect_diagnostic_payload(AppConfig(), _job_context(tmp_path))
    text = format_diagnostic_payload(payload)
    assert f"Media root: {tmp_path.resolve()}" in text


def test_media_root_absent_from_text_without_job(tmp_path: Path):
    payload = collect_diagnostic_payload(AppConfig())
    text = format_diagnostic_payload(payload)
    assert "Media root:" not in text
