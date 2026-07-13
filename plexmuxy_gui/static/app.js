const state = {
  appInfo: null, config: null, inputDir: "", planReport: null,
  runReport: null, loading: false, activeJobId: null, windowMaximized: false,
  settingsDirty: false, themeMode: "system", systemThemeQuery: null, navigationObserver: null,
  navigationTarget: null, navigationScrollCleanup: null, localeMode: "system",
  loadingMessageKey: "loading.initializing", lastJobStatus: null,
};

const THEME_STORAGE_KEY = "plexmuxy-theme";

const $ = (id) => document.getElementById(id);
const t = (key, variables = {}) => window.PlexMuxyI18n?.t(key, variables) ?? key;

window.addEventListener("pywebviewready", async () => {
  await initializeLocaleControls();
  bindEvents();
  initializeTheme();
  initializeNavigation();
  await initialize();
});
window.addEventListener("DOMContentLoaded", async () => {
  await initializeLocaleControls();
  bindEvents();
  initializeTheme();
  initializeNavigation();
  updateOptionAvailability();
  if (!window.pywebview) renderOfflineShell();
});

function bindEvents() {
  const bindings = [
    ["window-minimize-btn", "click", minimizeWindow], ["window-maximize-btn", "click", toggleMaximizeWindow],
    ["window-close-btn", "click", closeWindow], ["window-drag-region", "dblclick", toggleMaximizeWindow],
    ["sidebar-toggle", "click", toggleSidebar], ["sidebar-scrim", "click", closeSidebar],
    ["alert-close-btn", "click", clearError],
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
  document.querySelectorAll(".theme-option").forEach((button) => {
    if (button.classList.contains("language-option")) return;
    if (!button.dataset.boundClick) { button.addEventListener("click", chooseTheme); button.dataset.boundClick = "true"; }
  });
  document.querySelectorAll(".language-option").forEach((button) => {
    if (!button.dataset.boundClick) { button.addEventListener("click", chooseLocale); button.dataset.boundClick = "true"; }
  });
  document.querySelectorAll(".theme-menu").forEach((menu) => {
    if (!menu.dataset.boundToggle) { menu.addEventListener("toggle", closeSiblingMenus); menu.dataset.boundToggle = "true"; }
  });
  document.querySelectorAll(".step[href^='#']").forEach((link) => {
    if (!link.dataset.boundClick) { link.addEventListener("click", handleNavigationClick); link.dataset.boundClick = "true"; }
  });
  if (document.body && !document.body.dataset.boundResponsiveUi) {
    window.addEventListener("resize", syncSidebarAccessibility);
    window.addEventListener("plexmuxy:localechange", handleLocaleChange);
    document.addEventListener("keydown", handleGlobalKeyDown);
    document.body.dataset.boundResponsiveUi = "true";
  }
}

function closeSiblingMenus(event) {
  if (!event.currentTarget.open) return;
  document.querySelectorAll(".theme-menu[open]").forEach((menu) => {
    if (menu !== event.currentTarget) menu.open = false;
  });
}

async function initializeLocaleControls() {
  if (!window.PlexMuxyI18n) return;
  await window.PlexMuxyI18n.initialize();
  state.localeMode = window.PlexMuxyI18n.getMode();
  syncLocaleControls();
}

async function chooseLocale(event) {
  await window.PlexMuxyI18n?.setLocale(event.currentTarget.dataset.localeMode);
  const menu = $("language-menu");
  if (menu) menu.open = false;
}

function syncLocaleControls() {
  if (!window.PlexMuxyI18n) return;
  const mode = window.PlexMuxyI18n.getMode();
  const locale = window.PlexMuxyI18n.getLocale();
  state.localeMode = mode;
  const modeLabels = { system: t("language.system"), en: t("language.english"), "zh-CN": t("language.chinese") };
  const localeLabel = locale === "zh-CN" ? t("language.chinese") : t("language.english");
  setText("language-label", modeLabels[mode] || localeLabel);
  setText("language-detail", mode === "system" ? t("language.following", { language: localeLabel }) : t("language.fixed"));
  document.querySelectorAll(".language-option").forEach((button) => {
    const selected = button.dataset.localeMode === mode;
    button.classList.toggle("is-selected", selected);
    button.setAttribute("aria-pressed", String(selected));
  });
}

function handleLocaleChange() {
  syncLocaleControls();
  applyTheme(state.themeMode, false);
  if (state.appInfo) renderAppInfo();
  if (state.config) { renderConfigSummary(); renderRuntimeStatus(); }
  else if (!window.pywebview) renderOfflineShell();
  renderPlans(state.planReport);
  renderResults(state.runReport);
  if (state.lastJobStatus) renderProgress(state.lastJobStatus);
  if (state.loading) setText("loading-text", t(state.loadingMessageKey));
  if (state.activeJobId) setRuntimeStatus(t("status.jobRunning"));
}

function handleOverrideChange() {
  state.settingsDirty = true;
  updateOptionAvailability();
  clearReports();
}

function initializeTheme() {
  if (document.documentElement.dataset.themeReady === "true") return;
  document.documentElement.dataset.themeReady = "true";
  state.systemThemeQuery = window.matchMedia("(prefers-color-scheme: light)");
  const initialMode = document.documentElement.dataset.themeMode;
  state.themeMode = ["system", "light", "dark"].includes(initialMode) ? initialMode : "system";
  applyTheme(state.themeMode, false);
  state.systemThemeQuery.addEventListener("change", () => {
    if (state.themeMode === "system") applyTheme("system", false);
  });
}

function chooseTheme(event) {
  applyTheme(event.currentTarget.dataset.themeMode, true);
  const menu = $("theme-menu");
  if (menu) menu.open = false;
}

function applyTheme(mode, userInitiated) {
  if (!["system", "light", "dark"].includes(mode)) mode = "system";
  state.themeMode = mode;
  const resolved = mode === "system" ? (state.systemThemeQuery?.matches ? "light" : "dark") : mode;
  if (userInitiated) {
    document.documentElement.classList.add("theme-transition");
    window.setTimeout(() => document.documentElement.classList.remove("theme-transition"), 240);
    try { localStorage.setItem(THEME_STORAGE_KEY, mode); } catch (_) { /* Keep the in-memory choice. */ }
  }
  document.documentElement.dataset.themeMode = mode;
  document.documentElement.dataset.theme = resolved;
  const labels = { system: t("appearance.system"), light: t("appearance.light"), dark: t("appearance.dark") };
  setText("theme-label", labels[mode]);
  setText("theme-detail", mode === "system" ? t("appearance.following", { theme: labels[resolved] }) : t("appearance.fixed", { theme: labels[mode] }));
  document.querySelectorAll(".theme-option").forEach((button) => {
    const selected = button.dataset.themeMode === mode;
    button.classList.toggle("is-selected", selected);
    button.setAttribute("aria-pressed", String(selected));
  });
}

function initializeNavigation() {
  syncSidebarAccessibility();
  if (state.navigationObserver || !$("main-content")) return;
  const links = Array.from(document.querySelectorAll(".steps .step[href^='#']"));
  const sections = links.map((link) => document.querySelector(link.getAttribute("href"))).filter(Boolean);
  sections.sort((left, right) => left.offsetTop - right.offsetTop);
  const updateActiveSection = () => {
    if (state.navigationTarget) { setActiveNavigation(state.navigationTarget); return; }
    const main = $("main-content"); const rootTop = main.getBoundingClientRect().top;
    let current = sections[0];
    sections.forEach((section) => {
      if (section.getBoundingClientRect().top <= rootTop + 120) current = section;
    });
    if (main.scrollTop + main.clientHeight >= main.scrollHeight - 8) current = sections[sections.length - 1];
    if (current) setActiveNavigation("#" + current.id);
  };
  state.navigationObserver = new IntersectionObserver(() => {
    updateActiveSection();
  }, { root: $("main-content"), rootMargin: "-12% 0px -72% 0px", threshold: [0, 0.05] });
  sections.forEach((section) => state.navigationObserver.observe(section));
  $("app-shell").scrollTop = 0;
  if (window.location.hash && document.querySelector(window.location.hash)) {
    window.setTimeout(() => scrollToSection(window.location.hash, false), 0);
  } else {
    updateActiveSection();
  }
}

function handleNavigationClick(event) {
  event.preventDefault();
  const target = event.currentTarget.getAttribute("href");
  window.history.replaceState(null, "", target);
  setActiveNavigation(target);
  scrollToSection(target, true);
  closeSidebar(false);
}

function scrollToSection(targetSelector, smooth) {
  const main = $("main-content"); const target = document.querySelector(targetSelector);
  if (!main || !target) return;
  state.navigationScrollCleanup?.();
  state.navigationTarget = targetSelector;
  setActiveNavigation(targetSelector);
  $("app-shell").scrollTop = 0;
  const top = main.scrollTop + target.getBoundingClientRect().top - main.getBoundingClientRect().top - 24;
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const useSmoothScroll = smooth && !reducedMotion;
  let settleTimer = null;
  const releaseNavigationLock = () => {
    if (settleTimer) window.clearTimeout(settleTimer);
    main.removeEventListener("scroll", handleProgrammaticScroll);
    if (state.navigationTarget === targetSelector) {
      state.navigationTarget = null;
      setActiveNavigation(targetSelector);
    }
    if (state.navigationScrollCleanup === releaseNavigationLock) state.navigationScrollCleanup = null;
  };
  const handleProgrammaticScroll = () => {
    if (settleTimer) window.clearTimeout(settleTimer);
    settleTimer = window.setTimeout(releaseNavigationLock, 140);
  };
  state.navigationScrollCleanup = releaseNavigationLock;
  main.addEventListener("scroll", handleProgrammaticScroll, { passive: true });
  main.scrollTo({ top: Math.max(0, top), behavior: useSmoothScroll ? "smooth" : "auto" });
  if (useSmoothScroll) handleProgrammaticScroll();
  else window.requestAnimationFrame(releaseNavigationLock);
}

function setActiveNavigation(target) {
  document.querySelectorAll(".steps .step[href^='#']").forEach((link) => {
    const selected = link.getAttribute("href") === target;
    link.classList.toggle("active", selected);
    if (selected) link.setAttribute("aria-current", "step");
    else link.removeAttribute("aria-current");
  });
}

function toggleSidebar() {
  const open = !$("app-shell").classList.contains("sidebar-open");
  if (!open) { closeSidebar(true); return; }
  $("sidebar").inert = false;
  $("sidebar").removeAttribute("aria-hidden");
  $("app-shell").classList.toggle("sidebar-open", open);
  $("sidebar-toggle").setAttribute("aria-expanded", String(open));
  $("sidebar-toggle").setAttribute("aria-label", open ? t("sidebar.close") : t("sidebar.open"));
  window.setTimeout(() => $("sidebar").querySelector(".step.active")?.focus(), 210);
}

function closeSidebar(returnFocus = true) {
  const focusWasInside = $("sidebar")?.contains(document.activeElement);
  $("app-shell")?.classList.remove("sidebar-open");
  $("sidebar-toggle")?.setAttribute("aria-expanded", "false");
  $("sidebar-toggle")?.setAttribute("aria-label", t("sidebar.open"));
  syncSidebarAccessibility();
  if (returnFocus && focusWasInside) $("sidebar-toggle")?.focus();
}

function syncSidebarAccessibility() {
  const sidebar = $("sidebar"); const shell = $("app-shell");
  if (!sidebar || !shell) return;
  const hiddenOnMobile = window.innerWidth < 900 && !shell.classList.contains("sidebar-open");
  sidebar.inert = hiddenOnMobile;
  if (hiddenOnMobile) sidebar.setAttribute("aria-hidden", "true"); else sidebar.removeAttribute("aria-hidden");
}

function handleGlobalKeyDown(event) {
  if (event.key !== "Escape") return;
  if ($("app-shell")?.classList.contains("sidebar-open")) closeSidebar(true);
  if ($("theme-menu")) $("theme-menu").open = false;
  if ($("language-menu")) $("language-menu").open = false;
}

async function minimizeWindow() {
  try { await callApi("minimize_window"); } catch (error) { showError(error.message); }
}

async function toggleMaximizeWindow() {
  try {
    const result = await callApi("toggle_maximize_window");
    state.windowMaximized = Boolean(result.maximized);
    const button = $("window-maximize-btn");
    button.classList.toggle("is-maximized", state.windowMaximized);
    button.setAttribute("aria-pressed", String(state.windowMaximized));
    button.setAttribute("aria-label", state.windowMaximized ? t("window.restore") : t("window.maximize"));
    button.title = state.windowMaximized ? t("window.restoreShort") : t("window.maximizeShort");
  } catch (error) { showError(error.message); }
}

async function closeWindow() {
  try { await callApi("close_window"); } catch (error) { showError(error.message); }
}

async function initialize() {
  setLoading(true, "loading.initializing");
  try {
    state.appInfo = await callApi("get_app_info"); state.config = await callApi("load_config");
    renderAppInfo(); renderConfigSummary(); renderRuntimeStatus(); applyConfigDefaults();
  } catch (error) { showError(error.message); } finally { setLoading(false); }
}

function renderOfflineShell() {
  setRuntimeStatus(t("status.bridgeWaiting"), "warn");
  setText("sidebar-config-path", t("summary.waitingForBridge"));
  renderSummary($("config-summary"), [[t("summary.configPath"), t("summary.waitingForBridge")], [t("summary.configFile"), t("summary.unavailable")]]);
  renderSummary($("mkvmerge-summary"), [[t("summary.status"), t("summary.unavailable")], [t("summary.resolvedPath"), t("summary.waitingForBridge")]]);
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
    state.settingsDirty = false; updateRunButton();
    setRuntimeStatus(t("status.settingsSaved"), "ok");
  } catch (error) { showError(error.message); }
}

async function exportDiagnostics() {
  clearError();
  try {
    const result = await callApi("export_diagnostics");
    setRuntimeStatus(t("status.diagnostics", { path: result.path }), "ok");
  } catch (error) { showError(error.message); }
}

async function generatePlan() {
  clearError(); const payload = buildPayload();
  if (!payload.input_dir) { showError(t("error.chooseInput")); return; }
  setLoading(true, "loading.generatingPlan");
  try {
    state.planReport = await callApi("plan_job", payload); state.runReport = null;
    renderPlans(state.planReport); renderResults(null);
    if (state.planReport.error) showError(`${state.planReport.error_code || "PLAN_ERROR"}: ${state.planReport.error}`);
  } catch (error) { showError(error.message); } finally { setLoading(false); }
}

async function runMux() {
  clearError(); const payload = buildPayload();
  if (!state.planReport?.plans?.length || !state.planReport.snapshot) { showError(t("error.generatePlanFirst")); return; }
  const warnings = [];
  if (requiresDeleteConfirmation(payload)) warnings.push(t("error.deleteWarning"));
  if (payload.overrides.overwrite) warnings.push(t("error.overwriteWarning"));
  if (warnings.length && !await confirmAction(warnings.join(" "))) return;
  if (warnings.length) payload.yes = true;
  try {
    const started = await callApi("start_job", {snapshot: state.planReport.snapshot, yes: payload.yes});
    state.activeJobId = started.job_id; setJobRunning(true); await pollJob(started.job_id);
  } catch (error) { showError(error.message); setJobRunning(false); }
}

async function pollJob(jobId) {
  while (state.activeJobId === jobId) {
    const status = await callApi("get_job_status", jobId); state.lastJobStatus = status; renderProgress(status);
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
  try { await callApi("cancel_job", state.activeJobId); setRuntimeStatus(t("status.cancellationRequested"), "warn"); }
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

function confirmAction(message) {
  const dialog = $("confirm-dialog");
  setText("confirm-dialog-body", message + " " + t("confirm.review"));
  dialog.returnValue = "";
  dialog.showModal();
  return new Promise((resolve) => {
    dialog.addEventListener("close", () => resolve(dialog.returnValue === "confirm"), { once: true });
  });
}

async function callApi(method, payload) {
  if (!window.pywebview?.api?.[method]) throw new Error(t("error.bridgeUnavailable"));
  const response = payload === undefined ? await window.pywebview.api[method]() : await window.pywebview.api[method](payload);
  if (!response || response.ok !== true) throw new Error(response?.error || t("error.unknownApi"));
  return response.data;
}

function renderAppInfo() {
  if (!state.appInfo) return;
  setText("app-version", t("version", { version: state.appInfo.version })); setText("sidebar-config-path", state.appInfo.config_path || "");
}

function renderConfigSummary() {
  if (!state.config) return;
  renderSummary($("config-summary"), [
    [t("summary.configPath"), state.config.config_path], [t("summary.configFile"), state.config.config_exists ? t("summary.found") : t("summary.usingDefaults")],
    [t("summary.cleanup"), localizeEnum("value.cleanup", state.config.task.cleanup)], [t("summary.outputSuffix"), state.config.task.output_suffix],
    [t("summary.outputDirectory"), state.config.task.output_dir || t("summary.sourceFolder")], [t("summary.nameStrategy"), localizeEnum("value.nameStrategy", state.config.task.name_strategy)],
  ]);
  renderSummary($("mkvmerge-summary"), [
    [t("summary.status"), state.config.mkvmerge.available ? t("summary.available") : t("summary.notFound")],
    [t("summary.configuredPath"), state.config.mkvmerge.configured_path || t("summary.notSet")],
    [t("summary.resolvedPath"), state.config.mkvmerge.resolved_path || t("summary.notFound")],
  ]);
}

function renderRuntimeStatus() {
  const ready = Boolean(state.config?.mkvmerge.available);
  setRuntimeStatus(ready ? t("status.mkvmergeReady") : t("status.mkvmergeMissing"), ready ? "ok" : "warn");
}

function setRuntimeStatus(text, tone = "") {
  const container = $("runtime-status");
  if (!container) return;
  const label = container.querySelector("span:last-child");
  if (label) label.textContent = String(text ?? "");
  container.className = "runtime-status" + (tone ? " " + tone : "");
}

function applyConfigDefaults() {
  const task = state.config?.task; if (!task) return;
  $("cleanup").value = task.cleanup; $("extra-dir").value = task.extra_dir; $("output-suffix").value = task.output_suffix;
  $("output-dir").value = task.output_dir || ""; $("name-strategy").value = task.name_strategy;
  $("name-template").value = task.name_template || ""; $("overwrite").checked = Boolean(task.overwrite);
  state.settingsDirty = false; updateOptionAvailability(); updateRunButton();
}

function updateOptionAvailability() {
  const templateEnabled = $("name-strategy")?.value === "template";
  if ($("name-template")) {
    $("name-template").disabled = !templateEnabled;
    $("name-template").setAttribute("aria-disabled", String(!templateEnabled));
  }
}

function renderPlans(report) {
  const container = $("plans"); clear(container); clear($("plan-summary"));
  if (!report) return empty(container, "03", t("plan.empty.title"), t("plan.empty.detail"));
  $("plan-summary").append(
    badge(countText(report.plans.length, "count.plan.one", "count.plan.other"), "info"),
    badge(t("count.skipped", { count: report.skipped_files.length }), report.skipped_files.length ? "warn" : "ok")
  );
  report.plans.forEach((plan) => container.append(renderPlanCard(plan)));
  if (report.skipped_files.length) container.append(renderSkippedFiles(report.skipped_files, t("plan.skippedFiles")));
  container.className = "stack"; if (!container.childNodes.length) empty(container, "03", t("plan.empty.noPlansTitle"), t("plan.empty.noPlansDetail"));
}

function renderPlanCard(plan) {
  const article = element("article", "plan-card");
  const title = element("div", "card-title"); const heading = element("div");
  heading.append(element("h4", "", plan.source_video_name), element("div", "file-path", plan.source_video));
  title.append(heading, badge(plan.output_name, "info")); article.append(title, element("div", "file-path", t("plan.output", { path: plan.output_path })));
  const grid = element("div", "track-grid");
  grid.append(trackBox(t("plan.subtitles"), plan.subtitle_tracks, renderSubtitle), trackBox(t("plan.audio"), plan.audio_tracks, renderAudio), trackBox(t("plan.fonts"), plan.attachments, (item) => document.createTextNode(item.name)));
  article.append(grid);
  if (plan.cleanup_candidates?.length) article.append(trackBox(t("plan.cleanupCandidates"), plan.cleanup_candidates, (item) => itemNode(item.name, item.path)));
  if (plan.skipped_files?.length) article.append(renderSkippedFiles(plan.skipped_files, t("plan.planSkippedFiles")));
  return article;
}

function renderSubtitle(track) {
  const wrapper = element("div"); const flags = [track.default_track ? t("track.default") : "", track.forced_track ? t("track.forced") : ""].filter(Boolean);
  wrapper.append(document.createTextNode(`${track.name}${flags.length ? ` (${flags.join(", ")})` : ""}`));
  wrapper.append(element("div", "file-path", `${track.track_name} / ${track.mkv_language} / ${track.ietf_language}`), element("div", "file-path", track.match_reason)); return wrapper;
}
function renderAudio(track) { return itemNode(track.name, track.match_reason); }
function itemNode(text, detail) { const node = element("div", "", text); if (detail) node.append(element("div", "file-path", detail)); return node; }

function trackBox(title, items, renderer) {
  const box = element("div", "track-box"); box.append(element("h5", "", title));
  if (!items?.length) { box.append(element("div", "file-path", t("plan.none"))); return box; }
  const list = element("ul", "item-list"); items.forEach((item) => { const li = element("li"); li.append(renderer(item)); list.append(li); }); box.append(list); return box;
}

function renderSkippedFiles(skipped, title) { return trackBox(title, skipped, (item) => itemNode(item.name, `${item.reason} / ${item.stage}`)); }

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
  const container = $("job-progress"); clear(container);
  const card = element("div", "job-progress-card");
  const heading = element("div", "progress-heading");
  heading.append(element("strong", "", status.status === "running" ? t("progress.running") : status.status), element("span", "", completed + " / " + total));
  const progress = element("progress"); progress.max = Math.max(total, 1); progress.value = completed; progress.setAttribute("aria-label", t("progress.aria"));
  const meta = element("div", "progress-meta");
  meta.append(element("span", "", p.current_file || t("progress.preparing")), element("span", "", t("progress.counts", { succeeded: p.succeeded || 0, failed: p.failed || 0 })), element("span", "", t("progress.elapsed", { seconds: Number(status.elapsed_seconds || 0) })));
  card.append(heading, progress, meta); container.append(card);
}
function badge(text, type) { return element("span", `badge ${["ok", "warn", "danger", "info"].includes(type) ? type : ""}`, text); }
function element(tag, className = "", text = null) { const node = document.createElement(tag); if (className) node.className = className; if (text !== null) node.textContent = String(text); return node; }
function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }
function empty(container, number, title, detail) {
  clear(container); container.className = "stack empty-state";
  container.append(element("span", "empty-icon", number), element("h4", "", title), element("p", "", detail));
}
function setText(id, text) { $(id).textContent = String(text ?? ""); }

function clearReports() { state.planReport = null; state.runReport = null; renderPlans(null); renderResults(null); updateRunButton(); }
function updateRunButton() {
  const busy = state.loading || Boolean(state.activeJobId); const hasPlan = Boolean(state.planReport?.plans?.length);
  $("run-btn").disabled = busy || !hasPlan; $("plan-btn").disabled = busy; $("choose-dir-btn").disabled = busy;
  $("save-settings-btn").disabled = busy || !state.settingsDirty;
}
function showError(message) {
  setText("alert-message", message); $("alert").classList.remove("hidden");
  $("app-shell").scrollTop = 0; $("main-content").scrollTo({ top: 0, behavior: "auto" });
  $("alert").focus({ preventScroll: true });
}
function clearError() { setText("alert-message", ""); $("alert").classList.add("hidden"); }
function setLoading(value, messageKey = "activity.working") {
  state.loading = value; state.loadingMessageKey = messageKey;
  $("loading").classList.toggle("hidden", !value); setText("loading-text", t(messageKey)); updateRunButton();
}
function setJobRunning(value) {
  $("cancel-btn").classList.toggle("hidden", !value); $("cancel-btn").disabled = !value;
  if (value) setRuntimeStatus(t("status.jobRunning"), ""); else renderRuntimeStatus();
  updateRunButton();
}
