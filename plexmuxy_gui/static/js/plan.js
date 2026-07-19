function snapshotBaseline(edit) {
  edit.baseline = JSON.parse(JSON.stringify({
    enabled: edit.enabled,
    included_subtitles: edit.included_subtitles,
    included_external_audio: edit.included_external_audio,
    source_track_overrides: edit.source_track_overrides,
    subtitle_metadata_overrides: edit.subtitle_metadata_overrides,
    extra_subtitles: edit.extra_subtitles,
    extra_audio: edit.extra_audio,
    external_track_order: edit.external_track_order,
  }));
}

// Counts how many individual settings in one edit differ from its baseline.
// Derived fields (external_track_order) are excluded from the count so that
// toggling inclusion never double-counts alongside the order it implies.


function countEditChanges(edit) {
  const b = edit.baseline; if (!b) return 0;
  let n = 0;
  if (edit.enabled !== b.enabled) n += 1;
  n += symmetricDiffCount(edit.included_subtitles, b.included_subtitles);
  n += symmetricDiffCount(edit.included_external_audio, b.included_external_audio);
  n += overrideChanges(edit.source_track_overrides, b.source_track_overrides, "track_id");
  n += overrideChanges(edit.subtitle_metadata_overrides, b.subtitle_metadata_overrides, "path");
  return n;
}



function totalChangeCount() {
  let total = 0;
  state.planEdits.forEach((edit) => { total += countEditChanges(edit); });
  return total;
}



function symmetricDiffCount(a = [], b = []) {
  const setA = new Set(a), setB = new Set(b);
  let n = 0;
  setA.forEach((x) => { if (!setB.has(x)) n += 1; });
  setB.forEach((x) => { if (!setA.has(x)) n += 1; });
  return n;
}

// Counts overrides (keyed by track_id/path) whose state differs between the
// current and baseline arrays, counting both additions and removals once each.


function overrideChanges(current = [], baseline = [], key) {
  const baseById = new Map(baseline.map((o) => [o[key], o]));
  const curById = new Map(current.map((o) => [o[key], o]));
  let n = 0;
  current.forEach((item) => {
    const base = baseById.get(item[key]);
    if (!base || JSON.stringify(base) !== JSON.stringify(item)) n += 1;
  });
  baseline.forEach((item) => { if (!curById.has(item[key])) n += 1; });
  return n;
}

// Strips client-only bookkeeping (baseline/pristine) before sending an edit to
// the backend, which only understands the real plan fields.


function stripEdit(edit) {
  const { baseline, pristine, ...rest } = edit;
  return rest;
}

// Shows or hides the floating "Save" button and keeps its red-dot counter in
// sync with the number of unsaved setting changes.


function updateSaveButton() {
  const fab = $("plan-save-fab"); if (!fab) return;
  const count = totalChangeCount();
  const countEl = fab.querySelector(".fab-count");
  if (countEl) countEl.textContent = String(count);
  fab.classList.toggle("hidden", count === 0);
}



function setSaveSaving(saving) {
  const fab = $("plan-save-fab"); if (!fab) return;
  fab.disabled = saving;
  fab.classList.toggle("saving", saving);
  const label = fab.querySelector(".fab-label");
  if (label) label.textContent = saving ? t("plan.saving") : t("plan.save");
}



async function savePlanEdits() {
  if (!state.planReport?.snapshot || !state.planReport?.job_id) return;
  const edits = Array.from(state.planEdits.values()).filter((edit) => countEditChanges(edit) > 0);
  if (!edits.length) { updateSaveButton(); return; }
  state.planSaving = true; updateRunButton(); setSaveSaving(true);
  try {
    const payload = buildPayload();
    payload.job_id = state.planReport.job_id;
    payload.base_plan_id = state.planReport.snapshot.plan_id;
    payload.plan_edits = edits.map((edit) => stripEdit(edit));
    const report = await callApi("update_plan_draft", payload);
    // The backend recomputes the plan list, moving disabled plans (unchecked
    // "include" toggle) into `skipped_files`. Adopt the fresh lists so the top
    // counts stay accurate.
    const prevPlanIds = new Set((state.planReport.plans || []).map((p) => p.source_video));
    state.planReport.job_id = report.job_id;
    state.planReport.snapshot = report.snapshot;
    state.planReport.plans = report.plans;
    state.planReport.skipped_files = report.skipped_files;
    (report.plans || []).forEach((plan) => {
      const edit = state.planEdits.get(plan.source_video);
      if (edit) edit.revision = Number(plan.edit_revision || 0);
    });
    // Toggling a plan in/out changes membership, so rebuild the cards (the
    // disabled one moves to the skipped section). Other edits only change plan
    // contents, so refreshing the summary is enough and avoids disrupting
    // in-progress text inputs.
    const nextPlanIds = new Set((report.plans || []).map((p) => p.source_video));
    const membershipChanged = prevPlanIds.size !== nextPlanIds.size || [...prevPlanIds].some((id) => !nextPlanIds.has(id));
    // Auto-collapse plans that just became disabled (rendered inline as a minimal
    // card); expand plans that were just re-enabled.
    [...prevPlanIds].filter((id) => !nextPlanIds.has(id)).forEach((id) => state.collapsedCards.add(id));
    [...nextPlanIds].filter((id) => !prevPlanIds.has(id)).forEach((id) => state.collapsedCards.delete(id));
    // Rebaseline every saved edit so the saved values become the new "original";
    // the unsaved counter then drops to zero and the Save button hides. Done
    // before re-rendering so the button never shows a transient nonzero count.
    edits.forEach((edit) => snapshotBaseline(edit));
    if (membershipChanged) renderPlans(state.planReport);
    else renderPlanSummary(state.planReport);
    if (report.error) showError(`${report.error_code || "PLAN_ERROR"}: ${report.error}`);
    showToast(t("toast.planSaved.body"), "success", t("toast.planSaved.title"));
  } catch (error) {
    showToast(error.message, "error", t("toast.planSaveError.title"));
  } finally {
    state.planSaving = false; setSaveSaving(false); updateRunButton(); updateSaveButton();
  }
}



function buildPayload() {
  return { input_dir: $("input-dir").value.trim(), yes: false, overrides: {
    cleanup: getCustomSelectValue("cleanup"), extra_dir: $("extra-dir").value.trim(),
    output_suffix: $("output-suffix").value, output_dir: $("output-dir").value.trim(),
    name_strategy: getCustomSelectValue("name-strategy"), name_template: $("name-template").value.trim(),
    overwrite: $("overwrite").checked,
    font_mode: $("font-subset").checked ? "subset" : state.lastNonSubsetFontMode,
    mime_mode: getCustomSelectValue("font-mime-mode"),
    audio_filter_enabled: $("audio-filter-enabled").checked,
    exclude_audio_title_patterns: commaValues($("audio-exclude-patterns").value),
    keep_audio_languages: commaValues($("audio-keep-languages").value),
    keep_default_audio: $("keep-default-audio").checked,
    keep_all_when_unknown: $("keep-unknown-audio").checked,
    allow_no_audio: $("allow-no-audio").checked,
  }};
}



function commaValues(value) { return String(value || "").split(",").map((item) => item.trim()).filter(Boolean); }



function parsePathMappings(value) {
  return String(value || "").split(/\r?\n/).map((line) => line.trim()).filter(Boolean).map((line) => {
    const separator = line.indexOf("=");
    if (separator < 1) throw new Error(t("environment.plex.invalidMapping", { line }));
    return { local_root: line.slice(0, separator).trim(), server_root: line.slice(separator + 1).trim() };
  });
}



function requiresDeleteConfirmation(payload) {
  const task = state.config?.task || {}; const font = state.config?.font || {};
  return Boolean(payload.overrides.cleanup === "delete" || task.delete_original_video || task.delete_original_audio || task.delete_subtitle || font.delete_fonts_after_mux);
}



function confirmAction(message, options = {}) {
  const dialog = $("confirm-dialog");
  setText("confirm-dialog-title", options.title || t("confirm.title"));
  setText("confirm-dialog-body", options.review === false ? message : `${message} ${t("confirm.review")}`);
  setText("confirm-confirm-btn", options.confirmLabel || t("confirm.run"));
  dialog.classList.toggle("danger", Boolean(options.danger));
  dialog.returnValue = "";
  dialog.showModal();
  return new Promise((resolve) => {
    dialog.addEventListener("close", () => resolve(dialog.returnValue === "confirm"), { once: true });
  });
}



function renderPlans(report) {
  const container = $("plans"); clear(container);
  state.planSaving = false;
  if (!report) {
    clear($("plan-summary")); updateSaveButton(); state.planOrder = null; state.planData = null;
    return empty(container, "03", t("plan.empty.title"), t("plan.empty.detail"));
  }
  // Keep the latest full plan data for every source so a disabled plan can still
  // be rendered in place (and re-expanded instantly) instead of jumping to a
  // bottom section.
  state.planData = state.planData || new Map();
  (report.plans || []).forEach((plan) => state.planData.set(plan.source_video, plan));
  const disabledSources = new Map(
    (report.skipped_files || []).filter((s) => s.reason === "disabled_by_user").map((s) => [s.path, s])
  );
  syncPlanOrder(report, disabledSources);
  renderPlanSummary(report);
  state.planOrder.forEach((source) => {
    if (disabledSources.has(source)) {
      const cached = state.planData.get(source);
      if (cached) { container.append(renderPlanCard(cached, { collapsed: true, disabled: true })); return; }
      container.append(renderDisabledPlanCard(disabledSources.get(source)));
      return;
    }
    const plan = state.planData.get(source);
    if (plan) container.append(renderPlanCard(plan, { collapsed: state.collapsedCards.has(source) }));
  });
  const topSkipped = (report.skipped_files || []).filter((s) => s.reason !== "disabled_by_user");
  if (topSkipped.length) container.append(trackBox(t("plan.skippedFiles"), topSkipped, (item) => itemNode(item.name, `${item.reason} / ${item.stage}`)));
  container.className = "stack"; if (!container.childNodes.length) empty(container, "03", t("plan.empty.noPlansTitle"), t("plan.empty.noPlansDetail"));
}

// Keep a stable, ordered list of sources (active plans + in-place disabled ones)
// so a disabled plan stays where it was instead of jumping to the bottom.


function syncPlanOrder(report, disabledSources) {
  const current = [...(report.plans || []).map((p) => p.source_video), ...disabledSources.keys()];
  const existing = state.planOrder || [];
  const seen = new Set();
  const ordered = [];
  for (const source of existing) {
    if ((report.plans || []).some((p) => p.source_video === source) || disabledSources.has(source)) {
      ordered.push(source); seen.add(source);
    }
  }
  for (const source of current) if (!seen.has(source)) { ordered.push(source); seen.add(source); }
  state.planOrder = ordered;
}



function setCardCollapsed(source, collapsed) {
  const card = [...document.querySelectorAll(".plan-card")].find((el) => el.dataset.source === source);
  if (!card) return;
  card.classList.toggle("collapsed", collapsed);
  if (collapsed) state.collapsedCards.add(source); else state.collapsedCards.delete(source);
}



function togglePlanCollapse(source) {
  const card = [...document.querySelectorAll(".plan-card")].find((el) => el.dataset.source === source);
  if (!card) return;
  setCardCollapsed(source, !card.classList.contains("collapsed"));
}



function renderPlanSummary(report) {
  const summary = $("plan-summary"); clear(summary);
  summary.append(
    badge(countText(report.plans.length, "count.plan.one", "count.plan.other"), "info"),
    badge(t("count.skipped", { count: report.skipped_files.length }), report.skipped_files.length ? "warn" : "ok")
  );
  const fontPaths = new Set();
  report.plans.forEach((plan) => (plan.attachments || []).forEach((attachment) => {
    if (attachment.path) fontPaths.add(attachment.path);
  }));
  if (fontPaths.size) summary.append(badge(countText(fontPaths.size, "count.fonts.one", "count.fonts.other"), "info"));
  const languages = new Set();
  report.plans.forEach((plan) => (plan.subtitle_tracks || []).forEach((track) => {
    const mkv = (track.mkv_language || "").trim();
    const ietf = (track.ietf_language || "").trim();
    // Use the mkv+ietf pair as the identity: two languages can share the same
    // mkv code (e.g. chi for both zh-Hans and zh-Hant) yet differ by ietf.
    const key = `${mkv}|${ietf}`;
    if (mkv || ietf) languages.add(key);
  }));
  if (languages.size) summary.append(badge(countText(languages.size, "count.subtitleLanguages.one", "count.subtitleLanguages.other"), "info"));
  updateSaveButton();
}



function renderPlanCard(plan, { collapsed = false, disabled = false } = {}) {
  const article = element("article", "plan-card" + (collapsed ? " collapsed" : "") + (disabled ? " plan-card-disabled" : ""));
  article.dataset.source = plan.source_video;

  // Header: source filename plus the include-video toggle. The long source path
  // is shown once below (as the source folder) to avoid repeating the filename.
  const title = element("div", "card-title");
  const toggle = element("button", "plan-collapse", collapsed ? "▸" : "▾");
  toggle.type = "button"; toggle.title = t("plan.toggleCollapse");
  toggle.addEventListener("click", () => togglePlanCollapse(plan.source_video));
  const heading = element("div", "card-heading");
  heading.append(element("h4", "", plan.source_video_name));
  const enabledLabel = element("label", "plan-enabled toggle-row");
  const enabled = element("input"); enabled.type = "checkbox"; enabled.checked = currentPlanEdit(plan).enabled;
  enabled.addEventListener("change", () => {
    const edit = currentPlanEdit(plan);
    edit.enabled = enabled.checked;
    touchEdit(edit, article);
    // Immediate feedback: collapse on disable, expand on enable, and grey out
    // disabled cards — without waiting for the edit to be saved.
    article.classList.toggle("plan-card-disabled", !enabled.checked);
    setCardCollapsed(plan.source_video, !enabled.checked);
  });
  enabledLabel.append(enabled, element("span", "", t("plan.includeVideo")));
  title.append(toggle, heading, enabledLabel);
  if (disabled) title.append(badge(t("plan.disabledBadge"), "warn"));
  article.append(title);

  // Compact output name. When the output lands in the same folder as the
  // source, show only the output filename instead of the full path.
  const sourceDir = dirnameOf(plan.source_video);
  const outputDir = dirnameOf(plan.output_path);
  const outputDisplay = sourceDir && outputDir === sourceDir ? basenameOf(plan.output_path) : plan.output_path;
  const meta = element("div", "plan-meta");
  meta.append(element("div", "file-path plan-output", t("plan.output", { path: outputDisplay })));

  // "Add external file as track": opens a native picker rooted in the project
  // directory; the chosen file is classified by extension and dropped into the
  // matching section so the user can keep editing it. Shown on the same row as
  // the output filename (left/right) so the action reads as adding to this file.
  const addBtn = element("button", "ghost add-external-btn"); addBtn.type = "button";
  addBtn.append(iconSvg("icon-plus"), element("span", "", t("plan.addExternal")));
  addBtn.addEventListener("click", () => addExternalTrack(plan, article));

  const outputRow = element("div", "plan-output-row");
  outputRow.append(meta, addBtn);
  article.append(outputRow);
  const grid = element("div", "track-grid");
  const fontsBox = trackBox(t("plan.fonts"), plan.attachments, (item) => document.createTextNode(item.name), t("plan.attachmentCount", { count: plan.attachments.length }), "attachments-box");
  // When font subsetting is active for this plan, surface it as a badge to the
  // right of the attachment count so the mode is obvious at a glance.
  if (plan.font_subset_intent?.summary) fontsBox.firstElementChild?.append(badge(t("plan.fontSubsetBadge"), "info"));
  grid.append(renderSubtitleSection(plan), renderAudioSection(plan), fontsBox);
  article.append(grid);
  const subset = plan.font_subset_intent?.summary;
  if (subset) {
    const summary = element("div", "subset-summary");
    summary.append(
      element("strong", "", t("plan.fontSubset")),
      badge(t("plan.subsetFamilies", { count: subset.requested_family_count || 0 }), "info"),
      badge(t("plan.subsetFaces", { count: subset.matched_face_count || 0 }), "ok"),
      badge(t("plan.subsetAttachments", { count: subset.expected_attachment_count || 0 }), "info"),
      badge(t("plan.subsetFallbacks", { count: subset.fallback_family_count || 0 }), subset.fallback_family_count ? "warn" : "ok")
    );
    article.append(summary);
  }
  if (plan.skipped_files?.length) article.append(renderSkippedFiles(plan.skipped_files, t("plan.planSkippedFiles")));
  return article;
}



function currentPlanEdit(plan) {
  if (!state.planEdits.has(plan.source_video)) {
    const edit = {
      source_video: plan.source_video,
      revision: Number(plan.edit_revision || 0) + 1,
      enabled: true,
      included_subtitles: plan.subtitle_tracks.map((track) => track.path),
      included_external_audio: plan.audio_tracks.map((track) => track.path),
      source_track_overrides: [],
      subtitle_metadata_overrides: [],
      extra_subtitles: [],
      extra_audio: [],
      external_track_order: plan.external_track_order?.length ? [...plan.external_track_order] : [
        ...plan.subtitle_tracks.map((track) => `subtitle:${track.path}`),
        ...plan.audio_tracks.map((track) => `audio:${track.path}`),
      ],
    };
    snapshotBaseline(edit);
    state.planEdits.set(plan.source_video, edit);
  }
  return state.planEdits.get(plan.source_video);
}



function markPlanEdited(cardEl) {
  if (cardEl) cardEl.classList.add("has-edits");
  else document.querySelectorAll(".plan-card").forEach((card) => card.classList.add("has-edits"));
}



function touchEdit(edit, cardEl) { markPlanEdited(cardEl); updateSaveButton(); }

// Merges the external subtitle files (外挂) and the source container's own
// subtitle tracks (已有) into a single "字幕" section, mirroring renderAudioSection.


function renderSubtitleSection(plan) {
  const edit = currentPlanEdit(plan);
  const sourceSubs = (plan.source_tracks || []).filter((track) => track.type === "subtitle");
  const externalSubs = plan.subtitle_tracks || [];
  const box = element("div", "track-box editable-track-box");
  box.append(boxHeader(t("plan.subtitles"), t("plan.trackCount", { count: sourceSubs.length + externalSubs.length })));
  if (!sourceSubs.length && !externalSubs.length) {
    box.append(element("div", "file-path", t("plan.none")));
    return box;
  }
  const list = element("ul", "item-list");
  // External subtitles (外挂): include toggle + reorder + metadata editor.
  // Uses the same audio-row layout as external audio so the two sections match.
  externalSubs.forEach((track) => {
    const li = element("li", "audio-row"); li.dataset.trackPath = track.path;
    const label = element("label", "track-check");
    const input = element("input"); input.type = "checkbox"; input.checked = edit.included_subtitles.includes(track.path);
    input.addEventListener("change", () => {
      edit.included_subtitles = input.checked
        ? [...new Set([...edit.included_subtitles, track.path])]
        : edit.included_subtitles.filter((path) => path !== track.path);
      // A subtitle excluded from the draft can no longer carry metadata
      // overrides; drop them so the payload stays valid (the backend rejects
      // overrides that reference an excluded subtitle).
      if (!input.checked) {
        edit.subtitle_metadata_overrides = (edit.subtitle_metadata_overrides || []).filter((item) => item.path !== track.path);
        renderTrackBadges(badgeRow, externalBadge, effectiveSubtitleFlags(edit, track));
      }
      rebuildExternalOrder(edit);
      touchEdit(edit, li.closest(".plan-card"));
    });
    const copy = element("div", "source-track-copy");
    const badgeRow = element("div", "badge-row");
    const externalBadge = badge(t("plan.audioExternal"), "info");
    renderTrackBadges(badgeRow, externalBadge, effectiveSubtitleFlags(edit, track));
    copy.append(badgeRow, renderSubtitle(track));
    label.append(input, copy); li.append(label, makeDraggable(li, list, edit, "included_subtitles"));
    const details = element("details", "track-editor"); details.append(element("summary", "", t("plan.editMetadata")));
    const fields = element("div", "track-editor-fields");
    [
      ["track_name", track.track_name], ["mkv_language", track.mkv_language], ["ietf_language", track.ietf_language],
    ].forEach(([field, value]) => {
      const fieldLabel = element("label", ""); fieldLabel.append(element("span", "", t(`plan.field.${field}`)));
      const textInput = element("input"); textInput.type = "text"; textInput.value = value;
      textInput.addEventListener("input", () => syncSubtitleOverrideValue(edit, track, field, textInput.value));
      textInput.addEventListener("change", () => updateSubtitleOverride(edit, track, field, textInput.value, li.closest(".plan-card")));
      fieldLabel.append(textInput); fields.append(fieldLabel);
    });
    [["default_track", track.default_track], ["forced_track", track.forced_track]].forEach(([field, value]) => {
      const flag = element("label", "track-flag"); const checkbox = element("input"); checkbox.type = "checkbox"; checkbox.checked = Boolean(value);
      checkbox.addEventListener("change", () => {
        updateSubtitleOverride(edit, track, field, checkbox.checked, li.closest(".plan-card"));
        renderTrackBadges(badgeRow, externalBadge, effectiveSubtitleFlags(edit, track));
      });
      flag.append(checkbox, document.createTextNode(t(`plan.field.${field}`))); fields.append(flag);
    });
    details.append(fields); li.append(details);
    list.append(li);
  });
  // Source subtitles (已有): keep toggle + info.
  sourceSubs.forEach((track) => {
    const li = element("li", "audio-row");
    const label = element("label", "track-check");
    const input = element("input"); input.type = "checkbox";
    const existingOverride = edit.source_track_overrides.find((item) => item.track_id === track.id);
    input.checked = existingOverride ? existingOverride.included : track.included;
    input.addEventListener("change", () => {
      // Reverting a source track to its original inclusion drops the override,
      // so the unsaved-change counter decrements back to zero for that setting.
      edit.source_track_overrides = edit.source_track_overrides.filter((item) => item.track_id !== track.id);
      if (input.checked !== track.included) {
        edit.source_track_overrides.push({ track_id: track.id, included: input.checked });
      }
      touchEdit(edit, li.closest(".plan-card"));
    });
    const copy = element("div", "source-track-copy");
    const badgeRow = element("div", "badge-row");
    renderTrackBadges(badgeRow, badge(t("plan.audioSource"), "ok"), track);
    copy.append(
      badgeRow,
      element("strong", "", `${track.id} · ${track.title || t("plan.unknownTitle")}`)
    );
    appendMetaRows(copy, [metaRow("plan.field.language", track.language)]);
    const reasonSpan = decisionReasonSpan(track.decision_reason);
    if (reasonSpan) copy.append(reasonSpan);
    label.append(input, copy);
    li.append(label);
    list.append(li);
  });
  box.append(list);
  if (externalSubs.length) setupTrackDrag(list, edit, "included_subtitles");
  return box;
}

// Drag-to-reorder for external (外挂) track rows. Only the grip handle is
// draggable (NOT the whole <li>) — making the row itself draggable puts the
// metadata text inputs inside a draggable ancestor, which makes Chromium lag
// for several seconds on every focus/keystroke. Keeping the <li> non-draggable
// avoids that entirely while the handle still drives the reorder. Source (已有)
// rows have no data-track-path and act as a fixed boundary.


function makeDraggable(li, list, edit, selectedKey) {
  const handle = element("span", "track-drag-handle");
  handle.title = t("plan.dragToReorder");
  handle.setAttribute("aria-hidden", "true");
  const handleSvg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  handleSvg.setAttribute("viewBox", "0 0 10 16");
  handleSvg.setAttribute("width", "10");
  handleSvg.setAttribute("height", "16");
  handleSvg.setAttribute("fill", "currentColor");
  handleSvg.setAttribute("aria-hidden", "true");
  [[2.5, 3], [2.5, 8], [2.5, 13], [7.5, 3], [7.5, 8], [7.5, 13]].forEach(([cx, cy]) => {
    const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    dot.setAttribute("cx", String(cx));
    dot.setAttribute("cy", String(cy));
    dot.setAttribute("r", "1.5");
    handleSvg.appendChild(dot);
  });
  handle.appendChild(handleSvg);
  handle.setAttribute("draggable", "true");
  handle.addEventListener("dragstart", (e) => {
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", li.dataset.trackPath || "");
    // Build the drag ghost from a clone anchored at the cursor, so the preview
    // stays under the pointer instead of snapping to the row's top-left corner.
    const rect = li.getBoundingClientRect();
    const ghost = li.cloneNode(true);
    ghost.classList.remove("dragging");
    ghost.style.width = `${rect.width}px`;
    ghost.style.position = "fixed";
    ghost.style.top = "-9999px";
    ghost.style.left = "-9999px";
    ghost.style.pointerEvents = "none";
    document.body.appendChild(ghost);
    try { e.dataTransfer.setDragImage(ghost, e.clientX - rect.left, e.clientY - rect.top); } catch (_) { /* setDragImage unsupported */ }
    window.setTimeout(() => ghost.remove(), 0);
    li.classList.add("dragging");
  });
  handle.addEventListener("dragend", () => {
    li.classList.remove("dragging");
    const cardEl = li.closest(".plan-card");
    const before = edit[selectedKey].join("\u0000");
    const domOrder = [...list.querySelectorAll("li[data-track-path]")].map((el) => el.dataset.trackPath).filter(Boolean);
    // Preserve inclusion state: only reorder the included paths to match the
    // new visual order; excluded rows are ignored for the saved order.
    const next = domOrder.filter((path) => edit[selectedKey].includes(path));
    // Only persist when the order actually changed; no-op drags must not save.
    if (next.join("\u0000") === before) return;
    edit[selectedKey] = next;
    rebuildExternalOrder(edit);
    touchEdit(edit, cardEl);
  });
  return handle;
}



function getDragAfterElement(container, y) {
  const els = [...container.querySelectorAll("li[data-track-path]:not(.dragging)")];
  let closest = { offset: -Infinity, element: null };
  for (const child of els) {
    const box = child.getBoundingClientRect();
    const offset = y - box.top - box.height / 2;
    if (offset < 0 && offset > closest.offset) closest = { offset, element: child };
  }
  return closest.element;
}



function setupTrackDrag(list, edit, selectedKey) {
  list.addEventListener("dragover", (e) => {
    e.preventDefault();
    const dragging = list.querySelector("li.dragging");
    if (!dragging) return;
    const after = getDragAfterElement(list, e.clientY);
    const firstSource = list.querySelector("li:not([data-track-path])");
    if (after == null) {
      if (firstSource) list.insertBefore(dragging, firstSource);
      else list.appendChild(dragging);
    } else {
      list.insertBefore(dragging, after);
    }
  });
  list.addEventListener("drop", (e) => e.preventDefault());
}




function syncSubtitleOverrideValue(edit, track, field, value) {
  let override = edit.subtitle_metadata_overrides.find((item) => item.path === track.path);
  if (!override) { override = { path: track.path }; edit.subtitle_metadata_overrides.push(override); }
  override[field] = value;
  // If the override no longer differs from the original track values, drop it so
  // reverting a subtitle setting (e.g. toggling 默认 off then back on) counts as
  // zero unsaved changes.
  const original = {
    track_name: track.track_name, mkv_language: track.mkv_language, ietf_language: track.ietf_language,
    default_track: track.default_track, forced_track: track.forced_track,
  };
  const fields = ["track_name", "mkv_language", "ietf_language", "default_track", "forced_track"];
  const changed = fields.some((f) => override[f] !== original[f]);
  if (!changed) edit.subtitle_metadata_overrides = edit.subtitle_metadata_overrides.filter((item) => item.path !== track.path);
}



function updateSubtitleOverride(edit, track, field, value, cardEl) {
  syncSubtitleOverrideValue(edit, track, field, value);
  touchEdit(edit, cardEl);
}

// Merges both the external audio files (外挂) and the source container's own
// audio tracks (已有) into a single "音频" section, distinguishing them with a
// badge instead of splitting them across two separate panels.


function renderAudioSection(plan) {
  const edit = currentPlanEdit(plan);
  const sourceAudio = (plan.source_tracks || []).filter((track) => track.type === "audio");
  const externalAudio = plan.audio_tracks || [];
  const box = element("div", "track-box editable-track-box");
  box.append(boxHeader(t("plan.audio"), t("plan.trackCount", { count: sourceAudio.length + externalAudio.length })));
  if (!sourceAudio.length && !externalAudio.length) {
    box.append(element("div", "file-path", t("plan.none")));
    return box;
  }
  const list = element("ul", "item-list");
  // External audio (外挂): include toggle + reorder controls.
  externalAudio.forEach((track) => {
    const li = element("li", "audio-row"); li.dataset.trackPath = track.path;
    const label = element("label", "track-check");
    const input = element("input"); input.type = "checkbox";
    input.checked = edit.included_external_audio.includes(track.path);
    input.addEventListener("change", () => {
      edit.included_external_audio = input.checked
        ? [...new Set([...edit.included_external_audio, track.path])]
        : edit.included_external_audio.filter((path) => path !== track.path);
      rebuildExternalOrder(edit);
      touchEdit(edit, li.closest(".plan-card"));
    });
    const copy = element("div", "source-track-copy");
    copy.append(badge(t("plan.audioExternal"), "info"), renderAudio(track));
    label.append(input, copy);
    li.append(label, makeDraggable(li, list, edit, "included_external_audio"));
    list.append(li);
  });
  // Source audio (已有): keep toggle + preview.
  sourceAudio.forEach((track) => {
    const li = element("li", "audio-row");
    const label = element("label", "track-check");
    const input = element("input"); input.type = "checkbox";
    const existingOverride = edit.source_track_overrides.find((item) => item.track_id === track.id);
    input.checked = existingOverride ? existingOverride.included : track.included;
    input.addEventListener("change", () => {
      // Reverting a source track to its original inclusion drops the override,
      // so the unsaved-change counter decrements back to zero for that setting.
      edit.source_track_overrides = edit.source_track_overrides.filter((item) => item.track_id !== track.id);
      if (input.checked !== track.included) {
        edit.source_track_overrides.push({ track_id: track.id, included: input.checked });
      }
      touchEdit(edit, li.closest(".plan-card"));
    });
    const copy = element("div", "source-track-copy");
    copy.append(
      badge(t("plan.audioSource"), "ok"),
      element("strong", "", `${track.id} · ${track.title || t("plan.unknownTitle")}`)
    );
    appendMetaRows(copy, [
      metaRow("plan.field.codec", track.codec),
      metaRow("plan.field.language", track.language),
      metaRow("plan.field.channels", track.channels ? `${track.channels}ch` : null),
    ]);
    const reasonSpan = decisionReasonSpan(track.decision_reason);
    if (reasonSpan) copy.append(reasonSpan);
    label.append(input, copy);
    const preview = element("button", "ghost compact", t("plan.preview")); preview.type = "button";
    preview.disabled = !state.config?.ffmpeg?.available;
    preview.addEventListener("click", () => previewAudioTrack(plan, track, li, preview));
    li.append(label, preview);
    list.append(li);
  });
  box.append(list);
  if (externalAudio.length) setupTrackDrag(list, edit, "included_external_audio");
  return box;
}



async function previewAudioTrack(plan, track, row, button) {
  button.disabled = true;
  try {
    if (state.activePreviewId) await callApi("delete_audio_preview", state.activePreviewId);
    const result = await callApi("create_audio_preview", { snapshot: state.planReport.snapshot, source_video: plan.source_video, track_id: track.id, start_seconds: 60, duration_seconds: 15 });
    state.activePreviewId = result.preview_id;
    row.querySelector("audio")?.remove(); const player = element("audio", "audio-preview"); player.controls = true; player.src = result.uri; row.append(player); await player.play().catch(() => {});
  } catch (error) { showToast(error.message, "error", t("plan.previewFailed")); } finally { button.disabled = false; }
}

// Opens a native file picker (rooted in the project directory) so the user can
// add an external subtitle or audio file that the scan did not auto-match. The
// chosen file is classified by extension and dropped into the matching section;
// it is also recorded in the edit's extra_* list so the backend treats it as a
// manually-added input when the draft is saved.


async function addExternalTrack(plan, cardEl) {
  const inputDir = state.planReport?.snapshot?.input_dir || state.inputDir || $("input-dir").value.trim() || "";
  if (!inputDir) { showError(t("error.chooseInput")); return; }
  const startDir = dirnameOf(plan.source_video);
  let picked;
  try {
    picked = await callApi("choose_external_track", { input_dir: inputDir, start_dir: startDir });
  } catch (error) {
    showError(error.message); return;
  }
  if (!picked || picked.cancelled) return;
  const edit = currentPlanEdit(plan);
  const isSubtitle = picked.kind === "subtitle";
  const tracksKey = isSubtitle ? "subtitle_tracks" : "audio_tracks";
  const includedKey = isSubtitle ? "included_subtitles" : "included_external_audio";
  const extraKey = isSubtitle ? "extra_subtitles" : "extra_audio";
  if (plan[tracksKey].some((track) => track.path === picked.path)) {
    showToast(t("plan.addExternal.duplicate", { name: picked.name }), "warning");
    return;
  }
  const stem = picked.name.replace(/\.[^.]+$/, "");
  const track = isSubtitle
    ? { path: picked.path, name: picked.name, track_name: stem, mkv_language: "und", ietf_language: "und", default_track: false, forced_track: false, match_reason: "manual_assignment" }
    : { path: picked.path, name: picked.name, language: null, match_reason: "manual_assignment" };
  plan[tracksKey].push(track);
  edit[includedKey] = [...new Set([...edit[includedKey], picked.path])];
  edit[extraKey] = [...new Set([...(edit[extraKey] || []), picked.path])];
  rebuildExternalOrder(edit);
  touchEdit(edit, cardEl);
  renderPlans(state.planReport);
  showToast(t("plan.addExternal.added", { name: picked.name }), "success");
}



function rebuildExternalOrder(edit) {
  edit.external_track_order = [
    ...edit.included_subtitles.map((path) => `subtitle:${path}`),
    ...edit.included_external_audio.map((path) => `audio:${path}`),
  ];
}



function renderSubtitle(track) {
  const wrapper = element("div");
  wrapper.append(document.createTextNode(track.name));
  appendMetaRows(wrapper, [
    metaRow("plan.field.track_name", track.track_name),
    metaRow("plan.field.mkv_language", track.mkv_language),
    metaRow("plan.field.ietf_language", track.ietf_language),
    metaRow("plan.matchReason", localizeEnum("track.reason", track.match_reason)),
  ]);
  return wrapper;
}


function renderAudio(track) {
  const wrapper = element("div");
  wrapper.append(document.createTextNode(track.name));
  appendMetaRows(wrapper, [
    metaRow("plan.field.language", track.language),
    metaRow("plan.matchReason", localizeEnum("track.reason", track.match_reason)),
  ]);
  return wrapper;
}


function renderDisabledPlanCard(skip) {
  const article = element("article", "plan-card plan-card-disabled");
  article.dataset.source = skip.path;
  const title = element("div", "card-title");
  const heading = element("div", "card-heading");
  heading.append(element("h4", "", skip.name));
  const enabledLabel = element("label", "plan-enabled toggle-row");
  const enabled = element("input"); enabled.type = "checkbox"; enabled.checked = false;
  enabled.addEventListener("change", () => reincludeDisabledPlan(skip.path));
  enabledLabel.append(enabled, element("span", "", t("plan.includeVideo")));
  title.append(heading, enabledLabel);
  article.append(title);
  article.append(element("div", "file-path plan-skipped-note", t("plan.disabledNote")));
  return article;
}

// A plan disabled via the "include" toggle is re-included by checking its
// checkbox on the (collapsed) disabled card; see renderDisabledPlanCard.


function reincludeDisabledPlan(sourceVideo) {
  const edit = state.planEdits.get(sourceVideo);
  if (!edit) return;
  edit.enabled = true;
  touchEdit(edit, null);
}


