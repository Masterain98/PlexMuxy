const state = {
  appInfo: null,
  config: null,
  inputDir: "",
  planReport: null,
  runReport: null,
  loading: false,
};

const $ = (id) => document.getElementById(id);

window.addEventListener("pywebviewready", async () => {
  bindEvents();
  await initialize();
});

window.addEventListener("DOMContentLoaded", () => {
  bindEvents();
  if (!window.pywebview) {
    renderOfflineShell();
  }
});

function bindEvents() {
  const bindings = [
    ["choose-dir-btn", "click", chooseDirectory],
    ["open-config-btn", "click", openConfigLocation],
    ["plan-btn", "click", generatePlan],
    ["run-btn", "click", runMux],
    ["input-dir", "input", (event) => {
      state.inputDir = event.target.value;
      clearReports();
      updateRunButton();
    }],
    ["cleanup", "change", handleOverrideChange],
    ["extra-dir", "input", handleOverrideChange],
    ["output-suffix", "input", handleOverrideChange],
    ["output-dir", "input", handleOverrideChange],
    ["name-strategy", "change", handleOverrideChange],
    ["name-template", "input", handleOverrideChange],
    ["overwrite", "change", handleOverrideChange],
  ];

  bindings.forEach(([id, eventName, handler]) => {
    const element = $(id);
    const boundKey = `bound${eventName}`;
    if (element && !element.dataset[boundKey]) {
      element.addEventListener(eventName, handler);
      element.dataset[boundKey] = "true";
    }
  });
}

function handleOverrideChange() {
  clearReports();
  updateRunButton();
}

async function initialize() {
  setLoading(true, "Initializing...");
  try {
    state.appInfo = await callApi("get_app_info");
    state.config = await callApi("load_config");
    renderAppInfo();
    renderConfigSummary();
    renderRuntimeStatus();
    applyConfigDefaults();
  } catch (error) {
    showError(error.message);
  } finally {
    setLoading(false);
  }
}

function renderOfflineShell() {
  $("runtime-status").textContent = "Bridge waiting";
  $("runtime-status").className = "status-pill warn";
  $("config-summary").innerHTML = summaryHtml([
    ["Config path", "Waiting for pywebview"],
    ["Config file", "Unavailable"],
  ]);
  $("mkvmerge-summary").innerHTML = summaryHtml([
    ["Status", "Unavailable"],
    ["Resolved path", "Waiting for pywebview"],
  ]);
}

async function chooseDirectory() {
  clearError();
  try {
    const result = await callApi("choose_directory");
    if (!result.cancelled && result.path) {
      state.inputDir = result.path;
      $("input-dir").value = result.path;
      clearReports();
      updateRunButton();
    }
  } catch (error) {
    showError(error.message);
  }
}

async function openConfigLocation() {
  clearError();
  try {
    await callApi("open_config_location");
  } catch (error) {
    showError(error.message);
  }
}

async function generatePlan() {
  clearError();
  const payload = buildPayload();

  if (!payload.input_dir) {
    showError("Choose or enter an input directory first.");
    return;
  }

  setLoading(true, "Generating mux plan...");
  try {
    const report = await callApi("plan_job", payload);
    state.planReport = report;
    state.runReport = null;
    renderPlans(report);
    renderResults(null);
    updateRunButton();
  } catch (error) {
    showError(error.message);
  } finally {
    setLoading(false);
  }
}

async function runMux() {
  clearError();
  const payload = buildPayload();

  if (!state.planReport || !state.planReport.plans || state.planReport.plans.length === 0) {
    showError("Generate a plan before running mux.");
    return;
  }

  if (requiresDeleteConfirmation(payload)) {
    const ok = confirm("Delete cleanup is destructive. Continue?");
    if (!ok) return;
    payload.yes = true;
  }

  if (payload.overrides.overwrite) {
    const ok = confirm("Overwrite is enabled. Continue?");
    if (!ok) return;
  }

  setLoading(true, "Running mux jobs...");
  try {
    const report = await callApi("run_job", payload);
    state.runReport = report;
    renderResults(report);
  } catch (error) {
    showError(error.message);
  } finally {
    setLoading(false);
  }
}

function buildPayload() {
  return {
    input_dir: $("input-dir").value.trim(),
    yes: false,
    overrides: {
      cleanup: $("cleanup").value,
      extra_dir: $("extra-dir").value.trim(),
      output_suffix: $("output-suffix").value,
      output_dir: $("output-dir").value.trim(),
      name_strategy: $("name-strategy").value,
      name_template: $("name-template").value.trim(),
      overwrite: $("overwrite").checked,
    },
  };
}

function requiresDeleteConfirmation(payload) {
  const task = state.config && state.config.task ? state.config.task : {};
  const font = state.config && state.config.font ? state.config.font : {};
  return Boolean(
    payload.overrides.cleanup === "delete"
      || task.delete_original_video
      || task.delete_original_audio
      || task.delete_subtitle
      || font.delete_fonts_after_mux
  );
}

async function callApi(method, payload) {
  if (!window.pywebview || !window.pywebview.api || !window.pywebview.api[method]) {
    throw new Error("Desktop bridge is not available.");
  }

  const response = payload === undefined
    ? await window.pywebview.api[method]()
    : await window.pywebview.api[method](payload);

  if (!response || response.ok !== true) {
    throw new Error(response && response.error ? response.error : "Unknown API error");
  }

  return response.data;
}

function renderAppInfo() {
  if (!state.appInfo) return;
  $("app-version").textContent = `Version ${state.appInfo.version}`;
  $("sidebar-config-path").textContent = state.appInfo.config_path || "";
}

function renderConfigSummary() {
  if (!state.config) return;
  $("config-summary").innerHTML = summaryHtml([
    ["Config path", state.config.config_path],
    ["Config file", state.config.config_exists ? "Found" : "Using defaults"],
    ["Cleanup", state.config.task.cleanup],
    ["Output suffix", state.config.task.output_suffix],
    ["Output directory", state.config.task.output_dir || "Source folder"],
    ["Name strategy", state.config.task.name_strategy],
  ]);
  $("mkvmerge-summary").innerHTML = summaryHtml([
    ["Status", state.config.mkvmerge.available ? "Available" : "Not found"],
    ["Configured path", state.config.mkvmerge.configured_path || "Not set"],
    ["Resolved path", state.config.mkvmerge.resolved_path || "Not found"],
  ]);
}

function renderRuntimeStatus() {
  if (!state.config) return;
  const status = $("runtime-status");
  status.textContent = state.config.mkvmerge.available ? "mkvmerge ready" : "mkvmerge missing";
  status.className = state.config.mkvmerge.available ? "status-pill ok" : "status-pill warn";
}

function applyConfigDefaults() {
  if (!state.config) return;
  const task = state.config.task;
  $("cleanup").value = task.cleanup;
  $("extra-dir").value = task.extra_dir;
  $("output-suffix").value = task.output_suffix;
  $("output-dir").value = task.output_dir || "";
  $("name-strategy").value = task.name_strategy;
  $("name-template").value = task.name_template || "";
  $("overwrite").checked = Boolean(task.overwrite);
}

function renderPlans(report) {
  const container = $("plans");
  const summary = $("plan-summary");
  if (!report) {
    summary.innerHTML = "";
    container.className = "stack empty-state";
    container.textContent = "No plan generated.";
    return;
  }

  summary.innerHTML = [
    badge(`${report.plans.length} plans`, "info"),
    badge(`${report.skipped_files.length} skipped`, report.skipped_files.length ? "warn" : "ok"),
  ].join("");

  const cards = report.plans.map(renderPlanCard);
  const skipped = renderSkippedFiles(report.skipped_files, "Skipped files");
  container.className = "stack";
  container.innerHTML = cards.join("") + skipped;
  if (!container.innerHTML) {
    container.className = "stack empty-state";
    container.textContent = "No mux plans were generated.";
  }
}

function renderPlanCard(plan) {
  return `
    <article class="plan-card">
      <div class="card-title">
        <div>
          <h4>${escapeHtml(plan.source_video_name)}</h4>
          <div class="file-path">${escapeHtml(plan.source_video)}</div>
        </div>
        ${badge(plan.output_name, "info")}
      </div>
      <div class="file-path">Output: ${escapeHtml(plan.output_path)}</div>
      <div class="track-grid">
        ${trackBox("Subtitles", plan.subtitle_tracks, renderSubtitle)}
        ${trackBox("Audio", plan.audio_tracks, renderAudio)}
        ${trackBox("Fonts", plan.attachments, (item) => escapeHtml(item.name))}
      </div>
      ${renderCleanupCandidates(plan.cleanup_candidates)}
      ${renderSkippedFiles(plan.skipped_files, "Plan skipped files")}
    </article>
  `;
}

function renderSubtitle(track) {
  const flags = [
    track.default_track ? "default" : null,
    track.forced_track ? "forced" : null,
  ].filter(Boolean).join(", ");
  const flagText = flags ? ` (${escapeHtml(flags)})` : "";
  return `${escapeHtml(track.name)}${flagText}<div class="file-path">${escapeHtml(track.track_name)} / ${escapeHtml(track.mkv_language)} / ${escapeHtml(track.ietf_language)}</div><div class="file-path">${escapeHtml(track.match_reason)}</div>`;
}

function renderAudio(track) {
  return `${escapeHtml(track.name)}<div class="file-path">${escapeHtml(track.match_reason)}</div>`;
}

function trackBox(title, items, renderer) {
  const content = items && items.length
    ? `<ul class="item-list">${items.map((item) => `<li>${renderer(item)}</li>`).join("")}</ul>`
    : `<div class="file-path">None</div>`;
  return `<div class="track-box"><h5>${escapeHtml(title)}</h5>${content}</div>`;
}

function renderCleanupCandidates(candidates) {
  if (!candidates || !candidates.length) return "";
  const items = candidates.map((item) => `<li>${escapeHtml(item.name)}<div class="file-path">${escapeHtml(item.path)}</div></li>`).join("");
  return `<div class="track-box"><h5>Cleanup candidates</h5><ul class="item-list">${items}</ul></div>`;
}

function renderSkippedFiles(skipped, title) {
  if (!skipped || !skipped.length) return "";
  const items = skipped.map((item) => `
    <li>
      ${escapeHtml(item.name)}
      <div class="file-path">${escapeHtml(item.reason)} / ${escapeHtml(item.stage)}</div>
    </li>
  `).join("");
  return `<div class="track-box"><h5>${escapeHtml(title)}</h5><ul class="item-list">${items}</ul></div>`;
}

function renderResults(report) {
  const container = $("results");
  const summary = $("result-summary");
  if (!report) {
    summary.innerHTML = "";
    container.className = "stack empty-state";
    container.textContent = "No mux run yet.";
    return;
  }

  summary.innerHTML = [
    badge(`${report.success_count} succeeded`, report.failure_count ? "info" : "ok"),
    badge(`${report.failure_count} failed`, report.failure_count ? "warn" : "ok"),
    badge(`${report.cleanup_results.length} cleanup`, "info"),
  ].join("");

  const resultCards = report.results.map(renderResultCard).join("");
  const cleanup = renderCleanupResults(report.cleanup_results);
  container.className = "stack";
  container.innerHTML = resultCards + cleanup;
  if (!container.innerHTML) {
    container.className = "stack empty-state";
    container.textContent = "No mux results returned.";
  }
}

function renderResultCard(result) {
  const statusClass = result.success ? "ok" : "warn";
  const statusText = result.success ? "success" : "failed";
  const error = result.error ? `<div class="alert">${escapeHtml(result.error)}</div>` : "";
  return `
    <article class="result-card">
      <div class="card-title">
        <div>
          <h4>${escapeHtml(result.output_name)}</h4>
          <div class="file-path">${escapeHtml(result.output_path)}</div>
        </div>
        ${badge(statusText, statusClass)}
      </div>
      <div class="count-row">
        ${badge(result.verified ? "verified" : "not verified", result.verified ? "ok" : "warn")}
        ${badge(`${result.warnings.length} warnings`, result.warnings.length ? "warn" : "info")}
      </div>
      ${error}
    </article>
  `;
}

function renderCleanupResults(cleanupResults) {
  if (!cleanupResults || !cleanupResults.length) return "";
  const items = cleanupResults.map((item) => {
    const status = item.success ? "ok" : "failed";
    const destination = item.destination
      ? `<div class="file-path">Destination: ${escapeHtml(item.destination)}</div>`
      : "";
    const error = item.error ? `<div class="file-path">${escapeHtml(item.error)}</div>` : "";
    return `<li>${escapeHtml(item.action)} ${escapeHtml(item.name)} ${badge(status, item.success ? "ok" : "warn")}${destination}${error}</li>`;
  }).join("");
  return `<div class="track-box"><h5>Cleanup results</h5><ul class="item-list">${items}</ul></div>`;
}

function summaryHtml(rows) {
  return rows.map(([key, value]) => `
    <div class="summary-item">
      <div class="summary-key">${escapeHtml(key)}</div>
      <div class="summary-value">${escapeHtml(value)}</div>
    </div>
  `).join("");
}

function badge(text, type) {
  const safeType = ["ok", "warn", "info"].includes(type) ? type : "";
  return `<span class="badge ${safeType}">${escapeHtml(text)}</span>`;
}

function clearReports() {
  state.planReport = null;
  state.runReport = null;
  renderPlans(null);
  renderResults(null);
}

function updateRunButton() {
  const hasPlan = Boolean(state.planReport && state.planReport.plans && state.planReport.plans.length);
  $("run-btn").disabled = state.loading || !hasPlan;
  $("plan-btn").disabled = state.loading;
  $("choose-dir-btn").disabled = state.loading;
}

function showError(message) {
  const alert = $("alert");
  alert.textContent = message;
  alert.classList.remove("hidden");
}

function clearError() {
  const alert = $("alert");
  alert.textContent = "";
  alert.classList.add("hidden");
}

function setLoading(value, text) {
  state.loading = value;
  $("loading").classList.toggle("hidden", !value);
  $("loading-text").textContent = text || "Working...";
  updateRunButton();
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
