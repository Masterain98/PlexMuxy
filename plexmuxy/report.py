from __future__ import annotations

from .models import CleanupResult, JobReport, MuxPlan, PlanBuildResult, SkippedFile


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


def format_job_report(report: JobReport, dry_run: bool = False) -> str:
    lines: list[str] = []
    if dry_run:
        lines.append("Dry-run complete. No files were changed.")
    lines.append(f"Input: {report.input_dir}")
    lines.append(f"Plans: {len(report.plans)}")
    if report.snapshot is not None:
        lines.append(f"Plan ID: {report.snapshot.plan_id}")
    if report.error:
        lines.append(f"Error: [{report.error_code or 'PLEXMUXY_ERROR'}] {report.error}")
    if report.results:
        lines.append(f"Mux succeeded: {report.success_count}")
        lines.append(f"Mux failed: {report.failure_count}")
    lines.append("")

    for plan in report.plans:
        lines.extend(format_plan(plan))
        result = next((item for item in report.results if item.plan == plan), None)
        if result is not None:
            status = "success" if result.success else "failed"
            lines.append(f"Result: {status}")
            if result.error:
                lines.append(f"  error: [{result.error_code or 'PLEXMUXY_ERROR'}] {result.error}")
        lines.append("")

    if report.skipped_files:
        lines.append("Skipped files:")
        lines.extend(format_skipped_file(skipped) for skipped in report.skipped_files)
        lines.append("")

    if report.cleanup_results:
        lines.append("Cleanup:")
        lines.extend(format_cleanup_result(result) for result in report.cleanup_results)

    if report.warnings:
        lines.append("Warnings:")
        lines.extend(f"  - {warning}" for warning in report.warnings)

    return "\n".join(lines).rstrip()


def format_plan(plan: MuxPlan) -> list[str]:
    lines = [
        f"Plan: {plan.source_video.name}",
        f"Output: {plan.output_path}",
    ]
    if plan.subtitle_tracks:
        lines.append("Subtitle tracks:")
        for subtitle_track in plan.subtitle_tracks:
            default = "true" if subtitle_track.default_track else "false"
            forced = "true" if subtitle_track.forced_track else "false"
            lines.append(f"  + {subtitle_track.path.name}")
            lines.append(f"    language: {subtitle_track.track_name} / {subtitle_track.mkv_language} / {subtitle_track.ietf_language}")
            lines.append(f"    default: {default}")
            lines.append(f"    forced: {forced}")
            lines.append(f"    reason: {subtitle_track.match_reason}")
    if plan.audio_tracks:
        lines.append("Audio tracks:")
        for audio_track in plan.audio_tracks:
            lines.append(f"  + {audio_track.path.name}")
            lines.append(f"    reason: {audio_track.match_reason}")
    if plan.attachments:
        lines.append("Attachments:")
        for attachment in plan.attachments:
            lines.append(f"  + {attachment.path}")
    if plan.cleanup_candidates:
        lines.append("Cleanup candidates:")
        for candidate in plan.cleanup_candidates:
            lines.append(f"  + {candidate.name}")
    if plan.skipped_files:
        lines.append("Plan skipped files:")
        lines.extend(format_skipped_file(skipped) for skipped in plan.skipped_files)
    if plan.source_tracks:
        lines.append("Source tracks (preserved by default):")
        for source_track in plan.source_tracks:
            lines.append(f"  + {source_track.id}: {source_track.type} {source_track.language or 'und'} {source_track.title or ''}".rstrip())
    if plan.warnings:
        lines.extend(f"Warning: {warning}" for warning in plan.warnings)
    return lines


def format_skipped_file(skipped: SkippedFile) -> str:
    return f"  - {skipped.path.name}: {skipped.reason} ({skipped.stage})"


def format_cleanup_result(result: CleanupResult) -> str:
    status = "ok" if result.success else "failed"
    if result.destination is not None:
        return f"  - {result.action} {result.path.name} -> {result.destination} [{status}]"
    if result.error:
        return f"  - {result.action} {result.path.name} [{status}]: {result.error}"
    return f"  - {result.action} {result.path.name} [{status}]"
