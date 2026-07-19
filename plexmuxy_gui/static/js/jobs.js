async function runMux() {
  clearError(); const payload = buildPayload();
  if (!state.planReport?.plans?.length || !state.planReport.snapshot) { showError(t("error.generatePlanFirst")); return; }
  // Plan edits are only persisted via the floating Save button; starting the
  // mux job before saving would discard them, so block until everything is saved.
  if (totalChangeCount() > 0) { showError(t("error.saveEditsFirst")); return; }
  const warnings = [];
  if (requiresDeleteConfirmation(payload)) warnings.push(t("error.deleteWarning"));
  if (payload.overrides.overwrite) warnings.push(t("error.overwriteWarning"));
  if (warnings.length && !await confirmAction(warnings.join(" "))) return;
  if (warnings.length) payload.yes = true;
  try {
    const started = await callApi("start_job", {job_id: state.planReport.job_id, snapshot: state.planReport.snapshot, yes: payload.yes});
    state.activeJobId = started.job_id; setJobRunning(true); await pollJob(started.job_id);
  } catch (error) { showError(error.message); setJobRunning(false); }
}



async function pollJob(jobId) {
  while (state.activeJobId === jobId) {
    const status = await callApi("get_job_status", jobId); state.lastJobStatus = status; renderProgress(status);
    if (["completed", "failed", "cancelled", "interrupted"].includes(status.status)) {
      try { state.runReport = await callApi("get_job_report", jobId); renderResults(state.runReport); }
      catch (error) { showError(status.error || error.message); }
      const tone = status.status === "completed" ? "success" : status.status === "cancelled" ? "warning" : "error";
      showToast(status.error || t(`toast.job.${status.status}.body`), tone, t(`toast.job.${status.status}.title`));
      state.activeJobId = null; setJobRunning(false); return;
    }
    await new Promise((resolve) => window.setTimeout(resolve, 500));
  }
}



async function cancelJob() {
  if (!state.activeJobId) return;
  try { await callApi("cancel_job", state.activeJobId); showToast(t("toast.cancelRequested.body"), "warning", t("toast.cancelRequested.title")); }
  catch (error) { showError(error.message); }
}



async function checkUpdates() {
  try {
    const result = await callApi("check_updates", true);
    const message = result.error
      ? t("environment.updates.failed", { error: result.error })
      : result.update_available
        ? t("environment.updates.available", { version: result.latest_version, url: result.release_url || "" })
        : t("environment.updates.current", { version: result.current_version });
    setText("update-check-status", message);
    showToast(message, result.error ? "warning" : "success", t("environment.updates.title"));
  } catch (error) { showToast(error.message, "warning", t("environment.updates.title")); }
}



async function deleteAllJobs() {
  if (!state.jobs.length) return;
  if (await confirmAction(t("jobs.deleteAllConfirm"), { title: t("jobs.deleteAllTitle"), confirmLabel: t("jobs.deleteAll"), danger: true, review: false })) {
    try { await callApi("clear_jobs"); await loadJobs(); showToast(t("toast.jobsCleared.body", { count: state.jobs.length }), "success", t("toast.jobsCleared.title")); }
    catch (error) { showError(error.message); }
  }
}



async function loadJobs() {
  if (!window.pywebview?.api?.list_jobs) return;
  try {
    const result = await callApi("list_jobs", 100);
    state.jobs = result.jobs || []; state.queuePaused = Boolean(result.paused); renderJobs();
  } catch (error) { if (state.currentView === "jobs") showError(error.message); }
}



function renderJobs() {
  const container = $("jobs-list"); if (!container) return; clear(container);
  setText("queue-toggle-btn", state.queuePaused ? t("jobs.resume") : t("jobs.pause"));
  const deleteAllButton = $("delete-all-jobs-btn");
  if (deleteAllButton) deleteAllButton.disabled = !state.jobs.length;
  if (!state.jobs.length) return empty(container, "02", t("jobs.empty.title"), t("jobs.empty.detail"));
  state.jobs.forEach((job) => {
    const card = element("article", "job-history-card"); const heading = element("div", "card-title");
    const copy = element("div"); copy.append(element("h4", "", job.input_dir), element("div", "file-path", job.updated_at));
    heading.append(copy, badge(localizeEnum("jobs.state", job.state), ["completed"].includes(job.state) ? "ok" : ["failed"].includes(job.state) ? "danger" : ["cancelled", "interrupted"].includes(job.state) ? "warn" : "info")); card.append(heading);
    if (job.error_message) card.append(element("div", "inline-error", `${job.error_code || "JOB_ERROR"}: ${job.error_message}`));
    const actions = element("div", "button-row");
    if (job.state === "awaiting_review") {
      const review = element("button", "primary compact", t("jobs.review")); review.type = "button";
      review.addEventListener("click", () => openSavedJob(job.id)); actions.append(review);
    }
    if (job.state === "queued_for_execution") {
      const up = element("button", "ghost compact", t("jobs.moveUp")); up.type = "button";
      const down = element("button", "ghost compact", t("jobs.moveDown")); down.type = "button";
      up.addEventListener("click", () => moveQueuedJob(job, -1)); down.addEventListener("click", () => moveQueuedJob(job, 1)); actions.append(up, down);
    }
    if (["failed", "cancelled", "interrupted"].includes(job.state)) {
      const retry = element("button", "secondary compact", t("jobs.retry")); retry.type = "button";
      retry.addEventListener("click", async () => { await callApi("retry_job", job.id); await loadJobs(); }); actions.append(retry);
    }
    if (["completed", "failed", "cancelled", "interrupted"].includes(job.state)) {
      const view = element("button", "secondary compact", t("jobs.view")); view.type = "button";
      view.addEventListener("click", () => openSavedJob(job.id)); actions.append(view);
      const output = element("button", "ghost compact", t("jobs.openOutput")); output.type = "button";
      output.addEventListener("click", async () => { try { await callApi("open_job_output", job.id); } catch (error) { showError(error.message); } }); actions.append(output);
      if (job.state === "completed" && state.config?.plex?.enabled) {
        const plex = element("button", "ghost compact", t("jobs.retryPlex")); plex.type = "button";
        plex.addEventListener("click", async () => {
          plex.disabled = true;
          try {
            const result = await callApi("retry_plex_refresh", job.id);
            showToast(t("jobs.retryPlexSuccess", { count: result.results.length }), "success", t("jobs.retryPlex"));
          } catch (error) { showError(error.message); }
          finally { plex.disabled = false; }
        }); actions.append(plex);
      }
      const replan = element("button", "ghost compact", t("jobs.replan")); replan.type = "button";
      replan.addEventListener("click", async () => { await callApi("replan_job", job.id); await loadJobs(); }); actions.append(replan);
    }
    const diagnostics = element("button", "ghost compact", t("jobs.diagnostics")); diagnostics.type = "button";
    diagnostics.addEventListener("click", () => previewJobDiagnostics(job)); actions.append(diagnostics);
    const remove = element("button", "destructive compact", t("jobs.delete")); remove.type = "button";
    remove.addEventListener("click", async () => {
      if (await confirmAction(t("jobs.deleteConfirm"), { title: t("jobs.deleteTitle"), confirmLabel: t("jobs.delete"), danger: true, review: false })) {
        try { await callApi("delete_job", job.id); await loadJobs(); showToast(t("toast.jobDeleted.body"), "success", t("toast.jobDeleted.title")); }
        catch (error) { showError(error.message); }
      }
    }); actions.append(remove);
    card.append(actions); container.append(card);
  });
  container.className = "stack";
}



async function openSavedJob(jobId) {
  try {
    const saved = await callApi("load_job", jobId);
    state.inputDir = saved.job.input_dir; $("input-dir").value = saved.job.input_dir;
    if (saved.job.state === "awaiting_review") {
      state.planReport = saved.report; state.runReport = null; state.planEdits.clear(); renderPlans(state.planReport); renderResults(null);
    } else {
      state.runReport = saved.report; renderResults(state.runReport);
    }
    window.location.hash = saved.job.state === "awaiting_review" ? "#/workspace/plan-section" : "#/workspace/run-section";
    updateRunButton();
  } catch (error) { showError(error.message); }
}



async function moveQueuedJob(job, delta) {
  try { await callApi("reorder_job", { job_id: job.id, position: Math.max(0, Number(job.position || 0) + delta) }); await loadJobs(); }
  catch (error) { showError(error.message); }
}



async function toggleQueue() {
  try {
    await callApi(state.queuePaused ? "resume_queue" : "pause_queue");
    state.queuePaused = !state.queuePaused; renderJobs();
  } catch (error) { showError(error.message); }
}



async function renderFontCache() {
  if (!window.pywebview?.api?.get_font_cache || !$("font-cache-summary")) return;
  try {
    const cache = await callApi("get_font_cache");
    renderSummary($("font-cache-summary"), [
      [t("environment.cache.status"), cache.enabled ? t("summary.available") : t("summary.unavailable")],
      [t("environment.cache.entries"), String(cache.entries)],
      [t("environment.cache.size"), formatBytes(cache.size_bytes)],
      [t("environment.cache.limit"), formatBytes(cache.max_size_bytes)],
      [t("environment.cache.path"), cache.path],
    ]);
  } catch (error) { showToast(error.message, "error", t("environment.cache.title")); }
}



async function clearFontCache() {
  try { await callApi("clear_font_cache"); await renderFontCache(); showToast(t("environment.cache.cleared"), "success", t("environment.cache.title")); }
  catch (error) { showToast(error.message, "error", t("environment.cache.title")); }
}



function formatBytes(value) {
  const bytes = Number(value || 0); if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`;
}



function clearReports() { state.planReport = null; state.runReport = null; state.planEdits.clear(); renderPlans(null); renderResults(null); updateRunButton(); }


function updateRunButton() {
  const busy = state.loading || Boolean(state.activeJobId); const hasPlan = Boolean(state.planReport?.plans?.length);
  const hasUnappliedEdits = state.planSaving;
  $("run-btn").disabled = busy || !hasPlan || hasUnappliedEdits; $("plan-btn").disabled = busy; $("choose-dir-btn").disabled = busy;
  $("save-settings-btn").disabled = busy || !state.settingsDirty;
  if ($("save-environment-btn")) $("save-environment-btn").disabled = busy || !state.environmentDirty;
  ["input-dir", "cleanup", "extra-dir", "output-dir", "output-suffix", "name-strategy", "name-template", "font-subset", "overwrite", "audio-filter-enabled", "audio-exclude-patterns", "audio-keep-languages", "keep-default-audio", "keep-unknown-audio", "allow-no-audio"].forEach((id) => {
    const control = $(id); if (!control) return;
    control.disabled = busy;
    control.setAttribute("aria-disabled", String(busy));
  });
  if (!busy) updateOptionAvailability();
}
// All errors surface as non-blocking toasts so the UI never yanks the user's
// scroll position or forces them to a top "needs attention" panel mid-task.

