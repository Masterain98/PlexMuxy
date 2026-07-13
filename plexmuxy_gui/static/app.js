const state = {
  appInfo: null, config: null, inputDir: "", planReport: null,
  runReport: null, loading: false, activeJobId: null, windowMaximized: false,
  settingsDirty: false, environmentDirty: false, themeMode: "system", systemThemeQuery: null, navigationObserver: null,
  navigationTarget: null, navigationScrollCleanup: null, localeMode: "system",
  loadingMessageKey: "loading.initializing", lastJobStatus: null, currentView: "workspace",
  lastNonSubsetFontMode: "all",
};

const THEME_STORAGE_KEY = "plexmuxy-theme";
const selectSearch = new WeakMap();

const $ = (id) => document.getElementById(id);
const t = (key, variables = {}) => window.PlexMuxyI18n?.t(key, variables) ?? key;
window.PlexMuxyRequestClose = closeWindow;

window.addEventListener("pywebviewready", async () => {
  await initializeLocaleControls();
  bindEvents();
  initializeCustomSelects();
  initializeTheme();
  initializeNavigation();
  await initialize();
});
window.addEventListener("DOMContentLoaded", async () => {
  await initializeLocaleControls();
  bindEvents();
  initializeCustomSelects();
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
    ["skip-link", "click", skipToMainContent],
    ["alert-close-btn", "click", clearError],
    ["choose-dir-btn", "click", chooseDirectory], ["open-config-btn", "click", openConfigLocation],
    ["diagnostics-btn", "click", exportDiagnostics], ["save-settings-btn", "click", saveSettings],
    ["save-environment-btn", "click", saveEnvironmentSettings], ["test-notification-btn", "click", testNotification],
    ["plan-btn", "click", generatePlan], ["run-btn", "click", runMux], ["cancel-btn", "click", cancelJob],
    ["input-dir", "input", (event) => { state.inputDir = event.target.value; clearReports(); }],
    ["cleanup", "change", handleOverrideChange], ["extra-dir", "input", handleOverrideChange],
    ["output-suffix", "input", handleOverrideChange], ["output-dir", "input", handleOverrideChange],
    ["name-strategy", "change", handleOverrideChange], ["name-template", "input", handleOverrideChange],
    ["overwrite", "change", handleOverrideChange], ["font-subset", "change", handleFontSubsetChange],
    ["notifications-enabled", "change", handleEnvironmentChange],
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
  document.querySelectorAll(".dependency-browse").forEach((button) => {
    if (!button.dataset.boundClick) { button.addEventListener("click", chooseDependency); button.dataset.boundClick = "true"; }
  });
  document.querySelectorAll(".dependency-reset").forEach((button) => {
    if (!button.dataset.boundClick) { button.addEventListener("click", restoreAutomaticDependency); button.dataset.boundClick = "true"; }
  });
  if (document.body && !document.body.dataset.boundResponsiveUi) {
    window.addEventListener("resize", syncSidebarAccessibility);
    window.addEventListener("plexmuxy:localechange", handleLocaleChange);
    document.addEventListener("keydown", handleGlobalKeyDown);
    document.addEventListener("pointerdown", handleOutsideSelectPointer);
    window.addEventListener("hashchange", () => handleRoute(false));
    document.body.dataset.boundResponsiveUi = "true";
  }
}

function closeSiblingMenus(event) {
  if (!event.currentTarget.open) return;
  document.querySelectorAll(".theme-menu[open]").forEach((menu) => {
    if (menu !== event.currentTarget) menu.open = false;
  });
}

function skipToMainContent(event) {
  event.preventDefault();
  $("main-content")?.focus({ preventScroll: true });
}

async function initializeLocaleControls() {
  if (!window.PlexMuxyI18n) return;
  await window.PlexMuxyI18n.initialize();
  state.localeMode = window.PlexMuxyI18n.getMode();
  syncLocaleControls();
  syncCustomTooltips();
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
  syncCustomTooltips();
  syncCustomSelectLabels();
  applyTheme(state.themeMode, false);
  if (state.appInfo) renderAppInfo();
  if (state.config) { renderConfigSummary(); renderEnvironmentSettings(false); renderRuntimeStatus(); }
  else if (!window.pywebview) renderOfflineShell();
  renderPlans(state.planReport);
  renderResults(state.runReport);
  if (state.lastJobStatus) renderProgress(state.lastJobStatus);
  if (state.loading) setText("loading-text", t(state.loadingMessageKey));
  if (state.activeJobId) setRuntimeStatus(t("status.jobRunning"));
  updateRouteLabels();
}

function syncCustomTooltips() {
  document.querySelectorAll("[data-i18n-title]").forEach((node) => {
    node.dataset.tooltip = t(node.dataset.i18nTitle);
    node.removeAttribute("title");
  });
}

function handleOverrideChange() {
  state.settingsDirty = true;
  updateOptionAvailability();
  clearReports();
}

function handleFontSubsetChange() {
  if ($("font-subset").checked && state.config?.font?.mode !== "subset") {
    state.lastNonSubsetFontMode = state.config?.font?.mode || state.lastNonSubsetFontMode;
  }
  handleOverrideChange();
}

function handleEnvironmentChange() {
  state.environmentDirty = true;
  updateRunButton();
}

function initializeCustomSelects() {
  document.querySelectorAll("[data-custom-select]").forEach((root) => {
    if (root.dataset.boundSelect) return;
    const trigger = root.querySelector('[role="combobox"]');
    const options = Array.from(root.querySelectorAll('[role="option"]'));
    trigger.addEventListener("click", () => toggleCustomSelect(root, true));
    trigger.addEventListener("keydown", (event) => handleSelectTriggerKey(event, root));
    options.forEach((option) => {
      option.addEventListener("click", () => selectCustomOption(root, option, true));
      option.addEventListener("keydown", (event) => handleSelectOptionKey(event, root, option));
    });
    root.dataset.boundSelect = "true";
    setCustomSelectValue(trigger.id, trigger.dataset.value || options[0]?.dataset.value || "", false);
  });
}

function handleSelectTriggerKey(event, root) {
  const options = customSelectOptions(root);
  if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
    event.preventDefault();
    openCustomSelect(root, false);
    const selected = Math.max(0, options.findIndex((option) => option.getAttribute("aria-selected") === "true"));
    const index = event.key === "End" ? options.length - 1 : event.key === "Home" ? 0 : event.key === "ArrowUp" ? Math.max(0, selected - 1) : Math.min(options.length - 1, selected + 1);
    options[index]?.focus();
    return;
  }
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    toggleCustomSelect(root, true);
    return;
  }
  if (event.key === "Escape") { closeCustomSelect(root, true); return; }
  if (isTypeaheadKey(event)) {
    const match = findTypeaheadMatch(root, event.key);
    if (match) { event.preventDefault(); selectCustomOption(root, match, true, false); }
  }
}

function handleSelectOptionKey(event, root, option) {
  const options = customSelectOptions(root); const index = options.indexOf(option);
  if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
    event.preventDefault();
    const next = event.key === "Home" ? 0 : event.key === "End" ? options.length - 1 : event.key === "ArrowDown" ? (index + 1) % options.length : (index - 1 + options.length) % options.length;
    options[next]?.focus();
    return;
  }
  if (event.key === "Enter" || event.key === " ") { event.preventDefault(); selectCustomOption(root, option, true); return; }
  if (event.key === "Escape") { event.preventDefault(); closeCustomSelect(root, true); return; }
  if (event.key === "Tab") { closeCustomSelect(root, false); return; }
  if (isTypeaheadKey(event)) {
    const match = findTypeaheadMatch(root, event.key);
    if (match) { event.preventDefault(); match.focus(); }
  }
}

function isTypeaheadKey(event) {
  return event.key.length === 1 && !event.altKey && !event.ctrlKey && !event.metaKey;
}

function findTypeaheadMatch(root, character) {
  const now = Date.now(); const previous = selectSearch.get(root);
  const query = previous && now - previous.time < 700 ? previous.query + character : character;
  selectSearch.set(root, { query, time: now });
  const normalized = query.toLocaleLowerCase();
  return customSelectOptions(root).find((option) => option.textContent.trim().toLocaleLowerCase().startsWith(normalized));
}

function customSelectOptions(root) { return Array.from(root.querySelectorAll('[role="option"]')); }

function toggleCustomSelect(root, focusOption) {
  const trigger = root.querySelector('[role="combobox"]');
  if (trigger.disabled) return;
  if (trigger.getAttribute("aria-expanded") === "true") closeCustomSelect(root, true);
  else openCustomSelect(root, focusOption);
}

function openCustomSelect(root, focusOption = true) {
  closeAllCustomSelects(root);
  const trigger = root.querySelector('[role="combobox"]'); const listbox = root.querySelector('[role="listbox"]');
  listbox.hidden = false;
  trigger.setAttribute("aria-expanded", "true");
  root.classList.add("is-open");
  root.classList.remove("opens-up");
  const triggerRect = trigger.getBoundingClientRect(); const listRect = listbox.getBoundingClientRect();
  const below = window.innerHeight - triggerRect.bottom; const above = triggerRect.top;
  if (below < listRect.height + 12 && above > below) root.classList.add("opens-up");
  if (focusOption) {
    const selected = customSelectOptions(root).find((option) => option.getAttribute("aria-selected") === "true");
    (selected || customSelectOptions(root)[0])?.focus();
  }
}

function closeCustomSelect(root, restoreFocus = false) {
  const trigger = root.querySelector('[role="combobox"]'); const listbox = root.querySelector('[role="listbox"]');
  if (!trigger || !listbox) return;
  trigger.setAttribute("aria-expanded", "false");
  listbox.hidden = true;
  root.classList.remove("is-open", "opens-up");
  if (restoreFocus) trigger.focus();
}

function closeAllCustomSelects(except = null) {
  document.querySelectorAll("[data-custom-select].is-open").forEach((root) => { if (root !== except) closeCustomSelect(root, false); });
}

function handleOutsideSelectPointer(event) {
  document.querySelectorAll("[data-custom-select].is-open").forEach((root) => { if (!root.contains(event.target)) closeCustomSelect(root, false); });
}

function selectCustomOption(root, option, emitChange, restoreFocus = true) {
  const trigger = root.querySelector('[role="combobox"]');
  setCustomSelectValue(trigger.id, option.dataset.value, emitChange);
  closeCustomSelect(root, restoreFocus);
}

function setCustomSelectValue(id, value, emitChange = false) {
  const trigger = $(id); if (!trigger) return;
  const root = trigger.closest("[data-custom-select]");
  const options = customSelectOptions(root);
  const selected = options.find((option) => option.dataset.value === String(value)) || options[0];
  if (!selected) return;
  trigger.dataset.value = selected.dataset.value;
  options.forEach((option) => option.setAttribute("aria-selected", String(option === selected)));
  const label = trigger.querySelector("[data-select-label]");
  if (label) label.textContent = selected.textContent.trim();
  if (emitChange) trigger.dispatchEvent(new Event("change", { bubbles: true }));
}

function getCustomSelectValue(id) { return $(id)?.dataset.value || ""; }

function syncCustomSelectLabels() {
  document.querySelectorAll("[data-custom-select] [role=combobox]").forEach((trigger) => setCustomSelectValue(trigger.id, trigger.dataset.value, false));
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
  if (state.navigationObserver || !$("main-content")) { handleRoute(false); return; }
  const links = Array.from(document.querySelectorAll('.steps .step[data-route="workspace"]'));
  const sections = links.map((link) => $(link.dataset.section)).filter(Boolean);
  sections.sort((left, right) => left.offsetTop - right.offsetTop);
  const updateActiveSection = () => {
    if (state.navigationTarget) { setActiveNavigation(state.navigationTarget); return; }
    if (state.currentView !== "workspace") return;
    const main = $("main-content"); const rootTop = main.getBoundingClientRect().top;
    let current = sections[0];
    sections.forEach((section) => {
      if (section.getBoundingClientRect().top <= rootTop + 120) current = section;
    });
    if (main.scrollTop + main.clientHeight >= main.scrollHeight - 8) current = sections[sections.length - 1];
    if (current) setActiveNavigation(`#/workspace/${current.id}`);
  };
  state.navigationObserver = new IntersectionObserver(() => {
    updateActiveSection();
  }, { root: $("main-content"), rootMargin: "-12% 0px -72% 0px", threshold: [0, 0.05] });
  sections.forEach((section) => state.navigationObserver.observe(section));
  $("app-shell").scrollTop = 0;
  handleRoute(false);
}

function handleNavigationClick(event) {
  event.preventDefault();
  const target = event.currentTarget.getAttribute("href");
  window.history.replaceState(null, "", target);
  handleRoute(true);
  closeSidebar(false);
}

function parseRoute(hash = window.location.hash) {
  const normalized = String(hash || "").replace(/^#\/?/, "");
  const parts = normalized.split("/").filter(Boolean);
  if (parts[0] === "environment") return { view: "environment", section: null };
  if (parts[0] === "workspace") return { view: "workspace", section: parts[1] || "directory-section" };
  if (normalized && $(normalized)) return { view: "workspace", section: normalized };
  return { view: "workspace", section: "directory-section" };
}

function handleRoute(smooth = false) {
  const route = parseRoute();
  state.currentView = route.view;
  const workspace = $("workspace-view"); const environment = $("environment-view");
  const showWorkspace = route.view === "workspace";
  workspace?.classList.toggle("hidden", !showWorkspace);
  environment?.classList.toggle("hidden", showWorkspace);
  if (workspace) workspace.inert = !showWorkspace;
  if (environment) environment.inert = showWorkspace;
  updateRouteLabels();
  if (showWorkspace) {
    const section = $(route.section) ? route.section : "directory-section";
    const target = `#\/workspace/${section}`;
    setActiveNavigation(target);
    window.setTimeout(() => scrollToSection(`#${section}`, smooth), 0);
  } else {
    state.navigationScrollCleanup?.();
    state.navigationTarget = null;
    setActiveNavigation("#/environment");
    $("main-content")?.scrollTo({ top: 0, behavior: "auto" });
  }
}

function updateRouteLabels() {
  const environment = state.currentView === "environment";
  setText("topbar-context", environment ? t("topbar.system") : t("topbar.workspace"));
  setText("topbar-page", environment ? t("sidebar.environment.title") : t("topbar.newJob"));
  document.title = environment ? t("document.environmentTitle") : t("document.workspaceTitle");
}

function scrollToSection(targetSelector, smooth) {
  const main = $("main-content"); const target = document.querySelector(targetSelector);
  if (!main || !target) return;
  const navigationKey = `#/workspace/${target.id}`;
  state.navigationScrollCleanup?.();
  state.navigationTarget = navigationKey;
  setActiveNavigation(navigationKey);
  $("app-shell").scrollTop = 0;
  const top = main.scrollTop + target.getBoundingClientRect().top - main.getBoundingClientRect().top - 24;
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const useSmoothScroll = smooth && !reducedMotion;
  let settleTimer = null;
  const releaseNavigationLock = () => {
    if (settleTimer) window.clearTimeout(settleTimer);
    main.removeEventListener("scroll", handleProgrammaticScroll);
    if (state.navigationTarget === navigationKey) {
      state.navigationTarget = null;
      setActiveNavigation(navigationKey);
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
    if (selected) link.setAttribute("aria-current", link.dataset.route === "environment" ? "page" : "step");
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
  closeAllCustomSelects();
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
    button.dataset.tooltip = state.windowMaximized ? t("window.restoreShort") : t("window.maximizeShort");
    button.removeAttribute("title");
  } catch (error) { showError(error.message); }
}

async function closeWindow() {
  const dialog = $("close-dialog");
  if (dialog.open) return;
  const messageKey = state.activeJobId ? "close.descriptionRunning" : (state.settingsDirty || state.environmentDirty ? "close.descriptionUnsaved" : "close.description");
  setText("close-dialog-body", t(messageKey));
  dialog.returnValue = "";
  dialog.showModal();
  const confirmed = await new Promise((resolve) => {
    dialog.addEventListener("close", () => resolve(dialog.returnValue === "confirm"), { once: true });
  });
  if (!confirmed) return;
  try { await callApi("close_window"); } catch (error) { showError(error.message); }
}

async function initialize() {
  setLoading(true, "loading.initializing");
  try {
    state.appInfo = await callApi("get_app_info"); state.config = await callApi("load_config");
    renderAppInfo(); renderConfigSummary(); renderRuntimeStatus(); applyConfigDefaults(); renderEnvironmentSettings();
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
    renderConfigSummary(); renderEnvironmentSettings(false); renderRuntimeStatus(); applyConfigDefaults();
    state.settingsDirty = false; updateRunButton();
    showToast(t("toast.settingsSaved.body"), "success", t("toast.settingsSaved.title"));
  } catch (error) { showError(error.message); }
}

async function saveEnvironmentSettings() {
  clearError();
  try {
    state.config = await callApi("save_environment_settings", {
      mkvmerge_path: $("mkvmerge-path").value.trim(),
      ffmpeg_path: $("ffmpeg-path").value.trim(),
      unrar_path: $("unrar-path").value.trim(),
      notifications_enabled: $("notifications-enabled").checked,
    });
    state.environmentDirty = false;
    renderConfigSummary(); renderEnvironmentSettings(); renderRuntimeStatus(); updateRunButton();
    showToast(t("toast.environmentSaved.body"), "success", t("toast.environmentSaved.title"));
  } catch (error) { showToast(error.message, "error", t("toast.environmentError.title")); }
}

async function chooseDependency(event) {
  const dependency = event.currentTarget.dataset.dependency;
  try {
    const result = await callApi("choose_dependency", dependency);
    if (result.cancelled || !result.path) return;
    $(`${dependency}-path`).value = result.path;
    $(`${dependency}-detail`).textContent = t("environment.pendingSave");
    handleEnvironmentChange();
  } catch (error) { showToast(error.message, "error", t("toast.environmentError.title")); }
}

function restoreAutomaticDependency(event) {
  const dependency = event.currentTarget.dataset.dependency;
  $(`${dependency}-path`).value = "";
  $(`${dependency}-detail`).textContent = t("environment.autoPending");
  handleEnvironmentChange();
}

async function testNotification() {
  try {
    const data = await callApi("test_notification", { title: t("notification.test.title"), message: t("notification.test.message") });
    if (!data.capability?.available) {
      showToast(t("toast.notificationUnavailable.body"), "warning", t("toast.notificationUnavailable.title"));
      return;
    }
    if (!data.result?.sent) throw new Error(data.result?.error || t("error.notificationFailed"));
    showToast(t("toast.notificationSent.body"), "success", t("toast.notificationSent.title"));
  } catch (error) { showToast(error.message, "error", t("toast.environmentError.title")); }
}

async function exportDiagnostics() {
  clearError();
  try {
    const result = await callApi("export_diagnostics");
    showToast(t("toast.diagnostics.body", { path: result.path }), "success", t("toast.diagnostics.title"), {
      label: t("toast.diagnostics.open"),
      callback: async () => { try { await callApi("open_diagnostics_location"); } catch (error) { showToast(error.message, "error", t("toast.environmentError.title")); } },
    }, 12000);
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

function buildPayload() {
  return { input_dir: $("input-dir").value.trim(), yes: false, overrides: {
    cleanup: getCustomSelectValue("cleanup"), extra_dir: $("extra-dir").value.trim(),
    output_suffix: $("output-suffix").value, output_dir: $("output-dir").value.trim(),
    name_strategy: getCustomSelectValue("name-strategy"), name_template: $("name-template").value.trim(),
    overwrite: $("overwrite").checked,
    font_mode: $("font-subset").checked ? "subset" : state.lastNonSubsetFontMode,
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
  const dependencies = ["mkvmerge", "ffmpeg", "unrar"];
  renderSummary($("mkvmerge-summary"), dependencies.map((name) => {
    const dependency = state.config[name];
    return [name, dependency.available ? t("summary.available") : (dependency.required ? t("summary.notFound") : t("summary.optionalMissing"))];
  }));
}

function renderEnvironmentSettings(resetDirty = true) {
  if (!state.config) return;
  ["mkvmerge", "ffmpeg", "unrar"].forEach((name) => {
    const dependency = state.config[name];
    const input = $(`${name}-path`); const badgeNode = $(`${name}-status`); const detail = $(`${name}-detail`);
    if (resetDirty) input.value = dependency.configured_path || "";
    const missingRequired = dependency.required && !dependency.available;
    badgeNode.textContent = dependency.available ? t("summary.available") : (missingRequired ? t("summary.requiredMissing") : t("summary.optionalMissing"));
    badgeNode.className = `dependency-badge ${dependency.available ? "ok" : missingRequired ? "danger" : "muted"}`;
    const source = dependencySourceLabel(dependency.source);
    detail.textContent = dependency.resolved_path ? t("environment.resolvedDetail", { path: dependency.resolved_path, source }) : t("environment.unresolvedDetail", { source });
  });

  const notifications = state.config.notifications || {};
  const toggle = $("notifications-enabled"); const testButton = $("test-notification-btn"); const capability = $("notification-capability");
  if (resetDirty) toggle.checked = Boolean(notifications.enabled);
  toggle.disabled = !notifications.available;
  toggle.setAttribute("aria-disabled", String(!notifications.available));
  testButton.disabled = !notifications.available;
  capability.textContent = notifications.available ? t("environment.notifications.available") : t("environment.notifications.unavailable");
  if (notifications.reason) capability.dataset.tooltip = notifications.reason;
  else delete capability.dataset.tooltip;
  capability.removeAttribute("title");
  if (resetDirty) state.environmentDirty = false;
  updateRunButton();
}

function dependencySourceLabel(source) {
  if (String(source).startsWith("environment:")) return t("environment.source.environment");
  const key = `environment.source.${source}`;
  const translated = t(key);
  return translated === key ? t("environment.source.missing") : translated;
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
  setCustomSelectValue("cleanup", task.cleanup); $("extra-dir").value = task.extra_dir; $("output-suffix").value = task.output_suffix;
  $("output-dir").value = task.output_dir || ""; setCustomSelectValue("name-strategy", task.name_strategy);
  $("name-template").value = task.name_template || ""; $("overwrite").checked = Boolean(task.overwrite);
  const fontMode = state.config?.font?.mode || "all";
  if (fontMode !== "subset") state.lastNonSubsetFontMode = fontMode;
  $("font-subset").checked = fontMode === "subset";
  state.settingsDirty = false; updateOptionAvailability(); updateRunButton();
}

function updateOptionAvailability() {
  const templateEnabled = getCustomSelectValue("name-strategy") === "template";
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
  const subsetPlans = report.plans.filter((plan) => plan.font_subset_intent?.summary);
  if (subsetPlans.length) {
    const familyCount = subsetPlans.reduce((total, plan) => total + Number(plan.font_subset_intent.summary.requested_family_count || 0), 0);
    const attachmentCount = subsetPlans.reduce((total, plan) => total + Number(plan.font_subset_intent.summary.expected_attachment_count || 0), 0);
    $("plan-summary").append(badge(t("plan.subsetSummary", { families: familyCount, attachments: attachmentCount }), "info"));
  }
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
function element(tag, className = "", text = null) { const node = document.createElement(tag); if (className) node.className = className; if (text !== null) node.textContent = String(text); return node; }
function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }
function empty(container, number, title, detail) {
  clear(container); container.className = "stack empty-state";
  container.append(element("span", "empty-icon", number), element("h4", "", title), element("p", "", detail));
}
function setText(id, text) { $(id).textContent = String(text ?? ""); }

function showToast(message, tone = "info", title = "", action = null, timeout = 7000) {
  const region = $("toast-region"); if (!region) return;
  const toast = element("article", `toast ${["success", "warning", "error", "info"].includes(tone) ? tone : "info"}`);
  toast.setAttribute("role", tone === "error" ? "alert" : "status");
  const copy = element("div", "toast-copy");
  if (title) copy.append(element("strong", "", title));
  copy.append(element("p", "", message));
  toast.append(copy);
  if (action?.label && typeof action.callback === "function") {
    const actionButton = element("button", "toast-action", action.label); actionButton.type = "button";
    actionButton.addEventListener("click", async () => { await action.callback(); toast.remove(); });
    toast.append(actionButton);
  }
  const dismiss = element("button", "toast-dismiss", "×"); dismiss.type = "button"; dismiss.setAttribute("aria-label", t("toast.dismiss"));
  dismiss.addEventListener("click", () => toast.remove()); toast.append(dismiss); region.append(toast);
  if (timeout > 0) window.setTimeout(() => toast.remove(), timeout);
}

function clearReports() { state.planReport = null; state.runReport = null; renderPlans(null); renderResults(null); updateRunButton(); }
function updateRunButton() {
  const busy = state.loading || Boolean(state.activeJobId); const hasPlan = Boolean(state.planReport?.plans?.length);
  $("run-btn").disabled = busy || !hasPlan; $("plan-btn").disabled = busy; $("choose-dir-btn").disabled = busy;
  $("save-settings-btn").disabled = busy || !state.settingsDirty;
  if ($("save-environment-btn")) $("save-environment-btn").disabled = busy || !state.environmentDirty;
  ["input-dir", "cleanup", "extra-dir", "output-dir", "output-suffix", "name-strategy", "name-template", "font-subset", "overwrite"].forEach((id) => {
    const control = $(id); if (!control) return;
    control.disabled = busy;
    control.setAttribute("aria-disabled", String(busy));
  });
  if (!busy) updateOptionAvailability();
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
