from __future__ import annotations

from collections.abc import Callable

from .models import CleanupResult, JobReport, MuxPlan, PlanBuildResult, SkippedFile

Translator = Callable[..., str]


def format_plan_build_result(plan_result: PlanBuildResult) -> str:
    lines: list[str] = []
    if not plan_result.plans:
        lines.append("No mux plans were generated.")
    for plan in plan_result.plans:
        lines.extend(format_plan(plan))
        lines.append("")
    if plan_result.skipped_files:
        lines.append("Skipped files:")
        lines.extend(format_skipped_file(skipped) for skipped in plan_result.skipped_files)
    return "\n".join(lines).rstrip()


def format_job_report(report: JobReport, dry_run: bool = False, translate: Translator | None = None) -> str:
    lines: list[str] = []
    if dry_run:
        lines.append(label(translate, "report.dryRun", "Dry-run complete. No files were changed."))
    lines.append(label(translate, "report.input", "Input: {value}", value=report.input_dir))
    lines.append(label(translate, "report.plans", "Plans: {value}", value=len(report.plans)))
    if report.snapshot is not None:
        lines.append(label(translate, "report.planId", "Plan ID: {value}", value=report.snapshot.plan_id))
    if report.error:
        lines.append(label(translate, "report.error", "Error: [{code}] {message}", code=report.error_code or "PLEXMUXY_ERROR", message=report.error))
    if report.results:
        lines.append(label(translate, "report.muxSucceeded", "Mux succeeded: {value}", value=report.success_count))
        lines.append(label(translate, "report.muxFailed", "Mux failed: {value}", value=report.failure_count))
    lines.append("")

    for plan in report.plans:
        lines.extend(format_plan(plan, translate))
        result = next((item for item in report.results if item.plan == plan), None)
        if result is not None:
            status = label(translate, "report.success" if result.success else "report.failed", "success" if result.success else "failed")
            lines.append(label(translate, "report.result", "Result: {value}", value=status))
            if result.error:
                lines.append(label(translate, "report.indentedError", "  error: [{code}] {message}", code=result.error_code or "PLEXMUXY_ERROR", message=result.error))
            lines.extend(label(translate, "report.indentedWarning", "  warning: {message}", message=warning) for warning in result.warnings)
        lines.append("")

    if report.skipped_files:
        lines.append(label(translate, "report.skipped", "Skipped files:"))
        lines.extend(format_skipped_file(skipped, translate) for skipped in report.skipped_files)
        lines.append("")

    if report.cleanup_results:
        lines.append(label(translate, "report.cleanup", "Cleanup:"))
        lines.extend(format_cleanup_result(result, translate) for result in report.cleanup_results)

    if report.warnings:
        lines.append(label(translate, "report.warnings", "Warnings:"))
        lines.extend(f"  - {warning}" for warning in report.warnings)

    return "\n".join(lines).rstrip()


def format_plan(plan: MuxPlan, translate: Translator | None = None) -> list[str]:
    lines = [
        label(translate, "report.plan", "Plan: {value}", value=plan.source_video.name),
        label(translate, "report.output", "Output: {value}", value=plan.output_path),
    ]
    if plan.subtitle_tracks:
        lines.append(label(translate, "report.subtitleTracks", "Subtitle tracks:"))
        for subtitle_track in plan.subtitle_tracks:
            default = "true" if subtitle_track.default_track else "false"
            forced = "true" if subtitle_track.forced_track else "false"
            lines.append(f"  + {subtitle_track.path.name}")
            lines.append(label(translate, "report.language", "    language: {value}", value=f"{subtitle_track.track_name} / {subtitle_track.mkv_language} / {subtitle_track.ietf_language}"))
            lines.append(label(translate, "report.default", "    default: {value}", value=default))
            lines.append(label(translate, "report.forced", "    forced: {value}", value=forced))
            lines.append(label(translate, "report.reason", "    reason: {value}", value=subtitle_track.match_reason))
    if plan.audio_tracks:
        lines.append(label(translate, "report.audioTracks", "Audio tracks:"))
        for audio_track in plan.audio_tracks:
            lines.append(f"  + {audio_track.path.name}")
            lines.append(label(translate, "report.reason", "    reason: {value}", value=audio_track.match_reason))
    if plan.attachments:
        lines.append(label(translate, "report.attachments", "Attachments:"))
        for attachment in plan.attachments:
            lines.append(f"  + {attachment.path}")
    if plan.font_subset_intent is not None:
        summary = plan.font_subset_intent.summary
        lines.append(label(translate, "report.fontSubset", "Font subset intent:"))
        lines.append(label(translate, "report.subtitles", "  subtitles: {value}", value=summary.subtitle_count))
        lines.append(label(translate, "report.families", "  families: {value}", value=summary.requested_family_count))
        lines.append(label(translate, "report.matchedFaces", "  matched faces: {value}", value=summary.matched_face_count))
        lines.append(label(translate, "report.expectedAttachments", "  expected attachments: {value}", value=summary.expected_attachment_count))
        lines.append(label(translate, "report.fullFontFallbacks", "  full-font fallbacks: {value}", value=summary.fallback_family_count))
        lines.extend(
            f"  issue: [{issue.code}] {issue.message}"
            for issue in plan.font_subset_intent.issues
        )
    if plan.cleanup_candidates:
        lines.append(label(translate, "report.cleanupCandidates", "Cleanup candidates:"))
        for candidate in plan.cleanup_candidates:
            lines.append(f"  + {candidate.name}")
    if plan.skipped_files:
        lines.append(label(translate, "report.planSkipped", "Plan skipped files:"))
        lines.extend(format_skipped_file(skipped, translate) for skipped in plan.skipped_files)
    if plan.source_tracks:
        lines.append(label(translate, "report.sourceTracks", "Source tracks (preserved by default):"))
        for source_track in plan.source_tracks:
            lines.append(f"  + {source_track.id}: {source_track.type} {source_track.language or 'und'} {source_track.title or ''}".rstrip())
    if plan.warnings:
        lines.extend(f"Warning: {warning}" for warning in plan.warnings)
    return lines


def format_skipped_file(skipped: SkippedFile, translate: Translator | None = None) -> str:
    return label(translate, "report.skippedItem", "  - {name}: {reason} ({stage})", name=skipped.path.name, reason=skipped.reason, stage=skipped.stage)


def format_cleanup_result(result: CleanupResult, translate: Translator | None = None) -> str:
    status = label(translate, "report.ok" if result.success else "report.failed", "ok" if result.success else "failed")
    if result.destination is not None:
        return f"  - {result.action} {result.path.name} -> {result.destination} [{status}]"
    if result.error:
        return f"  - {result.action} {result.path.name} [{status}]: {result.error}"
    return f"  - {result.action} {result.path.name} [{status}]"


def label(translate: Translator | None, key: str, default: str, **values) -> str:
    if translate is None:
        return default.format(**values)
    return translate(key, default=default, **values)
