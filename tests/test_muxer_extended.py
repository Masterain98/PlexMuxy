import json
from types import SimpleNamespace

from plexmuxy.config import default_config
from plexmuxy.models import (
    AttachmentPlan,
    AudioTrackPlan,
    MuxPlan,
    SourceTrackInfo,
    SubtitleTrackPlan,
    VerificationResult,
)
from plexmuxy.muxer import build_mkvmerge_command, execute_mux_plan, inspect_source_tracks, verify_mux_output


class FakeProcess:
    def __init__(self, command, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        # The temporary output follows --output.
        from pathlib import Path
        Path(command[command.index("--output") + 1]).write_bytes(b"partial")

    def poll(self):
        return self.returncode

    def communicate(self):
        return self.stdout, self.stderr


def test_mkvmerge_command_uses_planned_attachment_name_and_mime(tmp_path):
    font = tmp_path / "cache-key.ttf"
    plan = MuxPlan(
        tmp_path / "source.mkv",
        tmp_path / "output.mkv",
        attachments=[AttachmentPlan(
            font,
            expected_name="PMX_DEMO-Regular.ttf",
            expected_mime_type="application/x-truetype-font",
        )],
    )

    command = build_mkvmerge_command(plan, plan.output_path, "mkvmerge")

    assert command[-6:] == [
        "--attachment-name",
        "PMX_DEMO-Regular.ttf",
        "--attachment-mime-type",
        "application/x-truetype-font",
        "--attach-file",
        str(font),
    ]


def test_mkvmerge_command_scopes_source_audio_filter_before_source_input(tmp_path):
    source = tmp_path / "source.mkv"
    plan = MuxPlan(
        source,
        tmp_path / "output.mkv",
        source_tracks=[
            SourceTrackInfo(0, "video"),
            SourceTrackInfo(1, "audio", included=True),
            SourceTrackInfo(2, "audio", included=False),
        ],
    )

    command = build_mkvmerge_command(plan, plan.output_path, "mkvmerge")

    assert command[:6] == ["mkvmerge", "--output", str(plan.output_path), "--audio-tracks", "1", str(source)]


def test_mkvmerge_command_uses_no_audio_only_for_source_input(tmp_path):
    source = tmp_path / "source.mkv"
    external = tmp_path / "external.mka"
    plan = MuxPlan(
        source,
        tmp_path / "output.mkv",
        source_tracks=[SourceTrackInfo(1, "audio", included=False)],
    )
    plan.audio_tracks.append(AudioTrackPlan(external, None, "exact"))

    command = build_mkvmerge_command(plan, plan.output_path, "mkvmerge")

    assert command[:5] == ["mkvmerge", "--output", str(plan.output_path), "--no-audio", str(source)]
    assert command[-1] == str(external)


def test_mkvmerge_command_sets_subtitle_bcp47_language_with_supported_option(tmp_path):
    subtitle = tmp_path / "Example.JPSC.ass"
    plan = MuxPlan(
        tmp_path / "source.mkv",
        tmp_path / "output.mkv",
        subtitle_tracks=[SubtitleTrackPlan(
            subtitle,
            "jp_sc Studio",
            "chi",
            "zh-Hans",
            True,
            False,
            "exact",
        )],
    )

    command = build_mkvmerge_command(plan, plan.output_path, "mkvmerge")

    assert "--language-ietf" not in command
    language_index = command.index("--language")
    assert command[language_index + 1] == "0:zh-Hans"
    assert command[-1] == str(subtitle)


def test_execute_mux_plan_success_uses_verified_temp_then_replaces(monkeypatch, tmp_path):
    source = tmp_path / "source.mkv"
    source.write_bytes(b"source")
    output = tmp_path / "output.mkv"
    plan = MuxPlan(source, output)
    config = default_config()
    monkeypatch.setattr("plexmuxy.muxer.resolve_mkvmerge_path", lambda config: "mkvmerge")
    monkeypatch.setattr("plexmuxy.muxer.subprocess.Popen", lambda command, **kwargs: FakeProcess(command))
    monkeypatch.setattr("plexmuxy.muxer.verify_mux_output", lambda *args: VerificationResult(True))
    result = execute_mux_plan(plan, config)
    assert result.success and result.verified
    assert output.read_bytes() == b"partial"


def test_execute_mux_plan_failure_renames_partial(monkeypatch, tmp_path):
    source = tmp_path / "source.mkv"
    source.write_bytes(b"source")
    output = tmp_path / "output.mkv"
    plan = MuxPlan(source, output)
    config = default_config()
    monkeypatch.setattr("plexmuxy.muxer.resolve_mkvmerge_path", lambda config: "mkvmerge")
    monkeypatch.setattr("plexmuxy.muxer.subprocess.Popen", lambda command, **kwargs: FakeProcess(command, 2, stderr="boom"))
    result = execute_mux_plan(plan, config)
    assert result.error_code == "MUX_EXECUTION_FAILED"
    assert (tmp_path / "output.mkv.failed").exists()


def test_execute_mux_plan_reports_missing_tool_and_existing_output(tmp_path):
    source = tmp_path / "source.mkv"
    output = tmp_path / "output.mkv"
    source.write_bytes(b"source")
    output.write_bytes(b"existing")
    plan = MuxPlan(source, output)
    assert execute_mux_plan(plan, default_config()).error_code == "OUTPUT_EXISTS"
    output.unlink()
    assert execute_mux_plan(plan, default_config()).error_code == "MKVMERGE_NOT_FOUND"


def test_verifier_rejects_invalid_json_and_missing_attachment(monkeypatch, tmp_path):
    output = tmp_path / "output.mkv"
    output.write_bytes(b"mkv")
    plan = MuxPlan(tmp_path / "source.mkv", output)
    monkeypatch.setattr("plexmuxy.muxer.subprocess.run", lambda *a, **k: SimpleNamespace(returncode=0, stdout="bad", stderr=""))
    assert verify_mux_output(plan, output, "mkvmerge").error_code == "OUTPUT_INVALID_CONTAINER"

    plan.attachments = [AttachmentPlan(tmp_path / "font.ttf")]
    payload = {"tracks": [{"type": "video", "properties": {}}], "attachments": []}
    monkeypatch.setattr("plexmuxy.muxer.subprocess.run", lambda *a, **k: SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr=""))
    assert verify_mux_output(plan, output, "mkvmerge").error_code == "ATTACHMENT_COUNT_MISMATCH"


def test_inspect_source_tracks_reads_properties(monkeypatch, tmp_path):
    payload = {"tracks": [{"id": 1, "type": "audio", "codec": "AAC", "properties": {"language": "eng", "track_name": "Main", "audio_channels": 2}}]}
    monkeypatch.setattr("plexmuxy.muxer.subprocess.run", lambda *a, **k: SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr=""))
    tracks = inspect_source_tracks(tmp_path / "source.mkv", "mkvmerge")
    assert tracks[0].language == "eng"
    assert tracks[0].channels == 2
