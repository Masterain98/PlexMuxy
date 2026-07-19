function renderSkippedFiles(skipped, title) { return trackBox(title, skipped, (item) => itemNode(item.name, `${item.reason} / ${item.stage}`)); }

// Minimal fallback for a disabled plan whose full data is not cached (rare);
// the normal path renders a disabled plan as a full in-place card instead.


function renderResults(report) {
  const container = $("results"); clear(container); clear($("result-summary"));
  if (!report) return empty(container, "04", t("run.empty.title"), t("run.empty.detail"));
  $("result-summary").append(badge(t("count.succeeded", { count: report.success_count }), report.failure_count ? "info" : "ok"), badge(t("count.failed", { count: report.failure_count }), report.failure_count ? "danger" : "ok"), badge(t("count.cleanup", { count: report.cleanup_results.length }), "info"));
  report.results.forEach((result) => container.append(renderResultCard(result)));
  if (report.cleanup_results.length) container.append(trackBox(t("result.cleanupResults"), report.cleanup_results, (item) => itemNode(`${item.action} ${item.name} [${item.success ? t("result.ok") : t("result.failed")}]`, item.destination || item.error)));
  container.className = "stack"; if (!container.childNodes.length) empty(container, "04", t("run.empty.noResultsTitle"), t("run.empty.noResultsDetail"));
}



function renderResultCard(result) {
  const card = element("article", "result-card"); const title = element("div", "card-title");
  const heading = itemNode(result.output_name, result.output_path); heading.firstChild && (heading.firstChild.className = "");
  title.append(heading, badge(result.success ? t("result.success") : t("result.failed"), result.success ? "ok" : "danger")); card.append(title);
  const counts = element("div", "count-row"); counts.append(badge(result.verified ? t("result.verified") : t("result.notVerified"), result.verified ? "ok" : "warn"), badge(countText(result.warnings.length, "count.warning.one", "count.warning.other"), result.warnings.length ? "warn" : "info")); card.append(counts);
  if (result.error) card.append(element("div", "inline-error", `${result.error_code ? `[${result.error_code}] ` : ""}${result.error}`)); return card;
}



function localizeEnum(prefix, value) {
  const key = `${prefix}.${value}`;
  const translated = t(key);
  return translated === key ? String(value ?? "") : translated;
}



function countText(count, singularKey, pluralKey) {
  return t(Number(count) === 1 ? singularKey : pluralKey, { count });
}



function renderSummary(container, rows) { clear(container); rows.forEach(([key, value]) => { const row = element("div", "summary-item"); row.append(element("div", "summary-key", key), element("div", "summary-value", value)); container.append(row); }); }


function renderProgress(status) {
  state.lastJobStatus = status;
  const p = status.progress || {};
  const completed = Number(p.completed || 0); const total = Number(p.total || 0);
  const completedFamilies = Number(p.completed_families || 0); const totalFamilies = Number(p.total_families || 0);
  const phase = p.phase || status.status || "running";
  const container = $("job-progress"); clear(container);
  const card = element("div", "job-progress-card");
  const heading = element("div", "progress-heading");
  heading.append(element("strong", "", localizeEnum("progress.phase", phase)), element("span", "", completed + " / " + total));
  const progress = element("progress"); progress.max = Math.max(total, 1); progress.value = completed; progress.setAttribute("aria-label", t("progress.aria"));
  const meta = element("div", "progress-meta");
  meta.append(element("span", "", p.current_file || t("progress.preparing")), element("span", "", t("progress.counts", { succeeded: p.succeeded || 0, failed: p.failed || 0 })), element("span", "", t("progress.elapsed", { seconds: Number(status.elapsed_seconds || 0) })));
  card.append(heading, progress, meta); container.append(card);
  if (totalFamilies || p.current_family) {
    const familyRow = element("div", "family-progress");
    const familyProgress = element("progress");
    familyProgress.max = Math.max(totalFamilies, 1); familyProgress.value = completedFamilies; familyProgress.setAttribute("aria-label", t("progress.familyAria"));
    familyRow.append(
      element("span", "", p.current_family || t("progress.preparingFamilies")),
      familyProgress,
      element("span", "", t("progress.familyCounts", { completed: completedFamilies, total: totalFamilies }))
    );
    card.append(familyRow);
  }
}


function badge(text, type) { return element("span", `badge ${["ok", "warn", "danger", "info"].includes(type) ? type : ""}`, text); }
// Track-level flags (默认 / 强制) rendered as badges next to the
// 外挂 / 已有 source-type badge, never inline after the filename.


function trackFlagBadges(track) {
  const badges = [];
  if (track.default_track) badges.push(badge(t("track.default"), "info"));
  if (track.forced_track) badges.push(badge(t("track.forced"), "warn"));
  return badges;
}
// Resolves a subtitle track's effective default/forced flags, honoring any
// per-track metadata override the user has toggled in the editor.


function effectiveSubtitleFlags(edit, track) {
  const override = edit.subtitle_metadata_overrides.find((item) => item.path === track.path);
  return {
    default_track: override && "default_track" in override ? override.default_track : track.default_track,
    forced_track: override && "forced_track" in override ? override.forced_track : track.forced_track,
  };
}
// (Re)populates a badge row with the source-type badge followed by the
// default/forced flag badges. Clearing first lets callers refresh the row
// (e.g. when a flag toggle changes) without rebuilding the whole section.


function renderTrackBadges(container, sourceBadge, trackLike) {
  clear(container);
  container.append(sourceBadge, ...trackFlagBadges(trackLike));
}
// The "过滤未启用，予以保留" reason is noise whenever audio filtering is off
// (the default), so it is suppressed entirely from the decision-reason line.


function decisionReasonSpan(reason) {
  if (!reason || reason === "preserve_filter_disabled") return null;
  return element("span", "decision-reason", localizeEnum("track.reason", reason));
}

