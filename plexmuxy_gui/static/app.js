const state = {
  appInfo: null, config: null, inputDir: "", planReport: null,
  runReport: null, loading: false, activeJobId: null,
};

const $ = (id) => document.getElementById(id);

window.addEventListener("pywebviewready", async () => { bindEvents(); await initialize(); });
window.addEventListener("DOMContentLoaded", () => {
  bindEvents();
  if (!window.pywebview) renderOfflineShell();
});

function bindEvents() {
  const bindings = [
    ["choose-dir-btn", "click", chooseDirectory], ["open-config-btn", "click", openConfigLocation],
    ["diagnostics-btn", "click", exportDiagnostics], ["save-settings-btn", "click", saveSettings],
    ["plan-btn", "click", generatePlan], ["run-btn", "click", runMux], ["cancel-btn", "click", cancelJob],
    ["input-dir", "input", (event) => { state.inputDir = event.target.value; clearReports(); }],
    ["cleanup", "change", handleOverrideChange], ["extra-dir", "input", handleOverrideChange],
    ["output-suffix", "input", handleOverrideChange], ["output-dir", "input", handleOverrideChange],
    ["name-strategy", "change", handleOverrideChange], ["name-template", "input", handleOverrideChange],
    ["overwrite", "change", handleOverrideChange],
  ];
  bindings.forEach(([id, eventName, handler]) => {
    const element = $(id); const key = `bound${eventName}`;
    if (element && !element.dataset[key]) { element.addEventListener(eventName, handler); element.dataset[key] = "true"; }
  });
}

function handleOverrideChange() { clearReports(); }

async function initialize() {
  setLoading(true, "Initializing...");
  try {
    state.appInfo = await callApi("get_app_info"); state.config = await callApi("load_config");
    renderAppInfo(); renderConfigSummary(); renderRuntimeStatus(); applyConfigDefaults();
  } catch (error) { showError(error.message); } finally { setLoading(false); }
}

function renderOfflineShell() {
  setText("runtime-status", "Bridge waiting"); $("runtime-status").className = "status-pill warn";
  renderSummary($("config-summary"), [["Config path", "Waiting for pywebview"], ["Config file", "Unavailable"]]);
  renderSummary($("mkvmerge-summary"), [["Status", "Unavailable"], ["Resolved path", "Waiting for pywebview"]]);
}

async function chooseDirectory() {
  clearError();
  try {
    const result = await callApi("choose_directory");
    if (!result.cancelled && result.path) { state.inputDir = result.path; $("input-dir").value = result.path; clearReports(); }
  } catch (error) { showError(error.message); }
}

async function openConfigLocation() {
  clearError(); try { await callApi("open_config_location"); } catch (error) { showError(error.message); }
}

async function saveSettings() {
  clearError();
  try {
    state.config = await callApi("save_settings", buildPayload().overrides);
    renderConfigSummary(); renderRuntimeStatus(); applyConfigDefaults();
    setText("runtime-status", "Settings saved");
  } catch (error) { showError(error.message); }
}

async function exportDiagnostics() {
  clearError();
  try {
    const result = await callApi("export_diagnostics");
    setText("runtime-status", `Diagnostics: ${result.path}`);
  } catch (error) { showError(error.message); }
}

async function generatePlan() {
  clearError(); const payload = buildPayload();
  if (!payload.input_dir) { showError("Choose or enter an input directory first."); return; }
  setLoading(true, "Generating mux plan...");
  try {
    state.planReport = await callApi("plan_job", payload); state.runReport = null;
    renderPlans(state.planReport); renderResults(null);
    if (state.planReport.error) showError(`${state.planReport.error_code || "PLAN_ERROR"}: ${state.planReport.error}`);
  } catch (error) { showError(error.message); } finally { setLoading(false); }
}

async function runMux() {
  clearError(); const payload = buildPayload();
  if (!state.planReport?.plans?.length || !state.planReport.snapshot) { showError("Generate a plan before running mux."); return; }
  if (requiresDeleteConfirmation(payload) && !confirm("Delete cleanup is destructive. Continue?")) return;
  if (requiresDeleteConfirmation(payload)) payload.yes = true;
  if (payload.overrides.overwrite && !confirm("Overwrite is enabled. Continue?")) return;
  if (payload.overrides.overwrite) payload.yes = true;
  try {
    const started = await callApi("start_job", {snapshot: state.planReport.snapshot, yes: payload.yes});
    state.activeJobId = started.job_id; setJobRunning(true); await pollJob(started.job_id);
  } catch (error) { showError(error.message); setJobRunning(false); }
}

async function pollJob(jobId) {
  while (state.activeJobId === jobId) {
    const status = await callApi("get_job_status", jobId); renderProgress(status);
    if (["completed", "failed", "cancelled"].includes(status.status)) {
      try { state.runReport = await callApi("get_job_report", jobId); renderResults(state.runReport); }
      catch (error) { showError(status.error || error.message); }
      state.activeJobId = null; setJobRunning(false); return;
    }
    await new Promise((resolve) => window.setTimeout(resolve, 500));
  }
}

async function cancelJob() {
  if (!state.activeJobId) return;
  try { await callApi("cancel_job", state.activeJobId); setText("job-progress", "Cancellation requested..."); }
  catch (error) { showError(error.message); }
}

function buildPayload() {
  return { input_dir: $("input-dir").value.trim(), yes: false, overrides: {
    cleanup: $("cleanup").value, extra_dir: $("extra-dir").value.trim(),
    output_suffix: $("output-suffix").value, output_dir: $("output-dir").value.trim(),
    name_strategy: $("name-strategy").value, name_template: $("name-template").value.trim(),
    overwrite: $("overwrite").checked,
  }};
}

function requiresDeleteConfirmation(payload) {
  const task = state.config?.task || {}; const font = state.config?.font || {};
  return Boolean(payload.overrides.cleanup === "delete" || task.delete_original_video || task.delete_original_audio || task.delete_subtitle || font.delete_fonts_after_mux);
}

async function callApi(method, payload) {
  if (!window.pywebview?.api?.[method]) throw new Error("Desktop bridge is not available.");
  const response = payload === undefined ? await window.pywebview.api[method]() : await window.pywebview.api[method](payload);
  if (!response || response.ok !== true) throw new Error(response?.error || "Unknown API error");
  return response.data;
}

function renderAppInfo() {
  if (!state.appInfo) return;
  setText("app-version", `Version ${state.appInfo.version}`); setText("sidebar-config-path", state.appInfo.config_path || "");
}

function renderConfigSummary() {
  if (!state.config) return;
  renderSummary($("config-summary"), [
    ["Config path", state.config.config_path], ["Config file", state.config.config_exists ? "Found" : "Using defaults"],
    ["Cleanup", state.config.task.cleanup], ["Output suffix", state.config.task.output_suffix],
    ["Output directory", state.config.task.output_dir || "Source folder"], ["Name strategy", state.config.task.name_strategy],
  ]);
  renderSummary($("mkvmerge-summary"), [
    ["Status", state.config.mkvmerge.available ? "Available" : "Not found"],
    ["Configured path", state.config.mkvmerge.configured_path || "Not set"],
    ["Resolved path", state.config.mkvmerge.resolved_path || "Not found"],
  ]);
}

function renderRuntimeStatus() {
  const ready = Boolean(state.config?.mkvmerge.available); setText("runtime-status", ready ? "mkvmerge ready" : "mkvmerge missing");
  $("runtime-status").className = ready ? "status-pill ok" : "status-pill warn";
}

function applyConfigDefaults() {
  const task = state.config?.task; if (!task) return;
  $("cleanup").value = task.cleanup; $("extra-dir").value = task.extra_dir; $("output-suffix").value = task.output_suffix;
  $("output-dir").value = task.output_dir || ""; $("name-strategy").value = task.name_strategy;
  $("name-template").value = task.name_template || ""; $("overwrite").checked = Boolean(task.overwrite);
}

function renderPlans(report) {
  const container = $("plans"); clear(container); clear($("plan-summary"));
  if (!report) return empty(container, "No plan generated.");
  $("plan-summary").append(badge(`${report.plans.length} plans`, "info"), badge(`${report.skipped_files.length} skipped`, report.skipped_files.length ? "warn" : "ok"));
  report.plans.forEach((plan) => container.append(renderPlanCard(plan)));
  if (report.skipped_files.length) container.append(renderSkippedFiles(report.skipped_files, "Skipped files"));
  container.className = "stack"; if (!container.childNodes.length) empty(container, "No mux plans were generated.");
}

function renderPlanCard(plan) {
  const article = element("article", "plan-card");
  const title = element("div", "card-title"); const heading = element("div");
  heading.append(element("h4", "", plan.source_video_name), element("div", "file-path", plan.source_video));
  title.append(heading, badge(plan.output_name, "info")); article.append(title, element("div", "file-path", `Output: ${plan.output_path}`));
  const grid = element("div", "track-grid");
  grid.append(trackBox("Subtitles", plan.subtitle_tracks, renderSubtitle), trackBox("Audio", plan.audio_tracks, renderAudio), trackBox("Fonts", plan.attachments, (item) => document.createTextNode(item.name)));
  article.append(grid);
  if (plan.cleanup_candidates?.length) article.append(trackBox("Cleanup candidates", plan.cleanup_candidates, (item) => itemNode(item.name, item.path)));
  if (plan.skipped_files?.length) article.append(renderSkippedFiles(plan.skipped_files, "Plan skipped files"));
  return article;
}

function renderSubtitle(track) {
  const wrapper = element("div"); const flags = [track.default_track ? "default" : "", track.forced_track ? "forced" : ""].filter(Boolean);
  wrapper.append(document.createTextNode(`${track.name}${flags.length ? ` (${flags.join(", ")})` : ""}`));
  wrapper.append(element("div", "file-path", `${track.track_name} / ${track.mkv_language} / ${track.ietf_language}`), element("div", "file-path", track.match_reason)); return wrapper;
}
function renderAudio(track) { return itemNode(track.name, track.match_reason); }
function itemNode(text, detail) { const node = element("div", "", text); if (detail) node.append(element("div", "file-path", detail)); return node; }

function trackBox(title, items, renderer) {
  const box = element("div", "track-box"); box.append(element("h5", "", title));
  if (!items?.length) { box.append(element("div", "file-path", "None")); return box; }
  const list = element("ul", "item-list"); items.forEach((item) => { const li = element("li"); li.append(renderer(item)); list.append(li); }); box.append(list); return box;
}

function renderSkippedFiles(skipped, title) { return trackBox(title, skipped, (item) => itemNode(item.name, `${item.reason} / ${item.stage}`)); }

function renderResults(report) {
  const container = $("results"); clear(container); clear($("result-summary"));
  if (!report) return empty(container, "No mux run yet.");
  $("result-summary").append(badge(`${report.success_count} succeeded`, report.failure_count ? "info" : "ok"), badge(`${report.failure_count} failed`, report.failure_count ? "warn" : "ok"), badge(`${report.cleanup_results.length} cleanup`, "info"));
  report.results.forEach((result) => container.append(renderResultCard(result)));
  if (report.cleanup_results.length) container.append(trackBox("Cleanup results", report.cleanup_results, (item) => itemNode(`${item.action} ${item.name} [${item.success ? "ok" : "failed"}]`, item.destination || item.error)));
  container.className = "stack"; if (!container.childNodes.length) empty(container, "No mux results returned.");
}

function renderResultCard(result) {
  const card = element("article", "result-card"); const title = element("div", "card-title");
  const heading = itemNode(result.output_name, result.output_path); heading.firstChild && (heading.firstChild.className = "");
  title.append(heading, badge(result.success ? "success" : "failed", result.success ? "ok" : "warn")); card.append(title);
  const counts = element("div", "count-row"); counts.append(badge(result.verified ? "verified" : "not verified", result.verified ? "ok" : "warn"), badge(`${result.warnings.length} warnings`, result.warnings.length ? "warn" : "info")); card.append(counts);
  if (result.error) card.append(element("div", "alert", `${result.error_code ? `[${result.error_code}] ` : ""}${result.error}`)); return card;
}

function renderSummary(container, rows) { clear(container); rows.forEach(([key, value]) => { const row = element("div", "summary-item"); row.append(element("div", "summary-key", key), element("div", "summary-value", value)); container.append(row); }); }
function renderProgress(status) { const p = status.progress || {}; renderSummary($("job-progress"), [["Phase", status.status], ["Progress", `${p.completed || 0} / ${p.total || 0}`], ["Current", p.current_file || "—"], ["Succeeded / failed", `${p.succeeded || 0} / ${p.failed || 0}`], ["Elapsed", `${status.elapsed_seconds}s`]]); }
function badge(text, type) { return element("span", `badge ${["ok", "warn", "info"].includes(type) ? type : ""}`, text); }
function element(tag, className = "", text = null) { const node = document.createElement(tag); if (className) node.className = className; if (text !== null) node.textContent = String(text); return node; }
function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }
function empty(container, text) { container.className = "stack empty-state"; container.textContent = text; }
function setText(id, text) { $(id).textContent = String(text ?? ""); }

function clearReports() { state.planReport = null; state.runReport = null; renderPlans(null); renderResults(null); updateRunButton(); }
function updateRunButton() { const hasPlan = Boolean(state.planReport?.plans?.length); $("run-btn").disabled = state.loading || Boolean(state.activeJobId) || !hasPlan; $("plan-btn").disabled = state.loading || Boolean(state.activeJobId); $("choose-dir-btn").disabled = state.loading || Boolean(state.activeJobId); }
function showError(message) { setText("alert", message); $("alert").classList.remove("hidden"); $("alert").focus(); }
function clearError() { setText("alert", ""); $("alert").classList.add("hidden"); }
function setLoading(value, text) { state.loading = value; $("loading").classList.toggle("hidden", !value); setText("loading-text", text || "Working..."); updateRunButton(); }
function setJobRunning(value) { $("cancel-btn").classList.toggle("hidden", !value); $("cancel-btn").disabled = !value; updateRunButton(); }
