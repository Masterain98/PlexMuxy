const state = {
  appInfo: null, config: null, inputDir: "", planReport: null,
  runReport: null, loading: false, activeJobId: null, windowMaximized: false,
  settingsDirty: false, environmentDirty: false, themeMode: "system", systemThemeQuery: null, navigationObserver: null,
  navigationTarget: null, navigationScrollCleanup: null, localeMode: "system",
  loadingMessageKey: "loading.initializing", lastJobStatus: null, currentView: "workspace",
  lastNonSubsetFontMode: "all",
  planEdits: new Map(), jobs: [], queuePaused: false, activePreviewId: null,
  planSaving: false, planSaveError: null,
  planOrder: null, planData: null, collapsedCards: new Set(),
  dependencyDrafts: { mkvmerge: null, ffmpeg: null, unrar: null }, dependencyBusy: {},
  currentDiagnosticsJobId: null,
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
    ["refresh-jobs-btn", "click", loadJobs],
    ["queue-toggle-btn", "click", toggleQueue], ["clear-font-cache-btn", "click", clearFontCache],
    ["delete-all-jobs-btn", "click", deleteAllJobs],
    ["diagnostics-export-btn", "click", exportDiagnosticsFromDialog],
    ["diagnostics-copy-btn", "click", copyDiagnosticsFromDialog],
    ["open-font-cache-btn", "click", () => callApi("open_font_cache_location")],
    ["check-updates-btn", "click", checkUpdates],
    ["input-dir", "input", (event) => { state.inputDir = event.target.value; clearReports(); }],
    ["cleanup", "change", handleOverrideChange], ["extra-dir", "input", handleOverrideChange],
    ["output-suffix", "input", handleOverrideChange], ["output-dir", "input", handleOverrideChange],
    ["name-strategy", "change", handleOverrideChange], ["name-template", "input", handleOverrideChange],
    ["overwrite", "change", handleOverrideChange], ["font-subset", "change", handleFontSubsetChange],
    ["audio-filter-enabled", "change", handleOverrideChange],
    ["audio-exclude-patterns", "input", handleOverrideChange], ["audio-keep-languages", "input", handleOverrideChange],
    ["keep-default-audio", "change", handleOverrideChange], ["keep-unknown-audio", "change", handleOverrideChange],
    ["allow-no-audio", "change", handleOverrideChange],
    ["notifications-enabled", "change", handleEnvironmentChange],
    ["font-cache-enabled", "change", handleEnvironmentChange], ["font-cache-max-size", "input", handleEnvironmentChange],
    ["font-cache-max-age", "input", handleEnvironmentChange], ["updates-enabled", "change", handleEnvironmentChange],
    ["plex-enabled", "change", handleEnvironmentChange], ["plex-server-url", "input", handleEnvironmentChange],
    ["plex-section-id", "input", handleEnvironmentChange], ["plex-token-env", "input", handleEnvironmentChange],
    ["plex-path-mappings", "input", handleEnvironmentChange],
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
  document.querySelectorAll(".dependency-auto-detect").forEach((button) => {
    if (!button.dataset.boundClick) { button.addEventListener("click", autoDetectDependency); button.dataset.boundClick = "true"; }
  });
  document.querySelectorAll("[data-project-link]").forEach((button) => {
    if (!button.dataset.boundClick) { button.addEventListener("click", openProjectLink); button.dataset.boundClick = "true"; }
  });
  const installUnrarButton = $("install-unrar-btn");
  if (installUnrarButton && !installUnrarButton.dataset.boundClick) { installUnrarButton.addEventListener("click", installUnrarFromRarlab); installUnrarButton.dataset.boundClick = "true"; }
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
  const modeLabels = { system: t("language.system"), en: t("language.english"), "zh-CN": t("language.chinese"), "zh-TW": t("language.traditionalChinese"), ru: t("language.russian") };
  const localeLabel = locale === "zh-CN" ? t("language.chinese") : (locale === "zh-TW" ? t("language.traditionalChinese") : (locale === "ru" ? t("language.russian") : t("language.english")));
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
  renderJobs(); renderFontCache();
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
  if (parts[0] === "jobs") return { view: "jobs", section: null };
  if (parts[0] === "about") return { view: "about", section: null };
  if (parts[0] === "workspace") return { view: "workspace", section: parts[1] || "directory-section" };
  if (normalized && $(normalized)) return { view: "workspace", section: normalized };
  return { view: "workspace", section: "directory-section" };
}

function handleRoute(smooth = false) {
  const route = parseRoute();
  state.currentView = route.view;
  const workspace = $("workspace-view"); const environment = $("environment-view"); const jobs = $("jobs-view"); const about = $("about-view");
  const showWorkspace = route.view === "workspace";
  workspace?.classList.toggle("hidden", !showWorkspace);
  environment?.classList.toggle("hidden", route.view !== "environment");
  jobs?.classList.toggle("hidden", route.view !== "jobs");
  about?.classList.toggle("hidden", route.view !== "about");
  if (workspace) workspace.inert = !showWorkspace;
  if (environment) environment.inert = route.view !== "environment";
  if (jobs) jobs.inert = route.view !== "jobs";
  if (about) about.inert = route.view !== "about";
  updateRouteLabels();
  if (showWorkspace) {
    const section = $(route.section) ? route.section : "directory-section";
    const target = `#\/workspace/${section}`;
    setActiveNavigation(target);
    window.setTimeout(() => scrollToSection(`#${section}`, smooth), 0);
  } else if (route.view === "environment") {
    state.navigationScrollCleanup?.();
    state.navigationTarget = null;
    setActiveNavigation("#/environment");
  } else if (route.view === "jobs") {
    state.navigationScrollCleanup?.(); state.navigationTarget = null; setActiveNavigation("#/jobs"); loadJobs();
    $("main-content")?.scrollTo({ top: 0, behavior: "auto" });
  } else {
    state.navigationScrollCleanup?.(); state.navigationTarget = null; setActiveNavigation("#/about");
    $("main-content")?.scrollTo({ top: 0, behavior: "auto" });
  }
}

function updateRouteLabels() {
  const environment = state.currentView === "environment";
  const jobs = state.currentView === "jobs";
  const about = state.currentView === "about";
  setText("topbar-context", environment ? t("topbar.system") : jobs ? t("sidebar.jobs.title") : about ? t("topbar.application") : t("topbar.workspace"));
  setText("topbar-page", environment ? t("sidebar.environment.title") : jobs ? t("jobs.title") : about ? t("sidebar.about.title") : t("topbar.newJob"));
  document.title = environment ? t("document.environmentTitle") : jobs ? t("jobs.title") : about ? t("document.aboutTitle") : t("document.workspaceTitle");
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
  document.querySelectorAll(".sidebar .step[href^='#']").forEach((link) => {
    const selected = link.getAttribute("href") === target;
    link.classList.toggle("active", selected);
    if (selected) link.setAttribute("aria-current", link.dataset.section ? "step" : "page");
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
    await Promise.all([loadJobs(), renderFontCache()]);
    if (state.appInfo.activation_job_id) {
      await openSavedJob(state.appInfo.activation_job_id);
      if (state.appInfo.activation_action === "output") {
        try { await callApi("open_job_output", state.appInfo.activation_job_id); } catch (error) { showError(error.message); }
      }
    }
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
      mkvmerge_path: dependencyPathForSave("mkvmerge"),
      ffmpeg_path: dependencyPathForSave("ffmpeg"),
      unrar_path: dependencyPathForSave("unrar"),
      notifications_enabled: $("notifications-enabled").checked,
      font_cache_enabled: $("font-cache-enabled").checked,
      font_cache_max_size_mb: Number($("font-cache-max-size").value),
      font_cache_max_age_days: Number($("font-cache-max-age").value),
      updates_enabled: $("updates-enabled").checked,
      plex_enabled: $("plex-enabled").checked,
      plex_server_url: $("plex-server-url").value.trim(),
      plex_section_id: $("plex-section-id").value.trim(),
      plex_token_env: $("plex-token-env").value.trim(),
      plex_path_mappings: parsePathMappings($("plex-path-mappings").value),
    });
    state.dependencyDrafts = { mkvmerge: null, ffmpeg: null, unrar: null };
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
    state.dependencyDrafts[dependency] = mapResultToDraft(result, "manual");
    handleEnvironmentChange();
    renderDependency(dependency);
  } catch (error) { showToast(error.message, "error", t("toast.environmentError.title")); }
}

async function autoDetectDependency(event) {
  const dependency = event.currentTarget.dataset.dependency;
  setDependencyBusy(dependency, "checking");
  try {
    const result = await callApi("detect_dependency", dependency);
    state.dependencyDrafts[dependency] = mapResultToDraft(result, "auto-detect");
    handleEnvironmentChange();
  } catch (error) {
    showToast(error.message, "error", t("toast.environmentError.title"));
  } finally {
    setDependencyBusy(dependency, null);
    renderDependency(dependency);
  }
}

async function installUnrarFromRarlab() {
  setDependencyBusy("unrar", "downloading");
  try {
    const result = await callApi("install_unrar_from_rarlab");
    state.dependencyDrafts.unrar = mapResultToDraft(result, "download");
    handleEnvironmentChange();
  } catch (error) {
    showToast(error.message, "error", t("toast.environmentError.title"));
  } finally {
    setDependencyBusy("unrar", null);
    renderDependency("unrar");
  }
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
    state.planReport = await callApi("plan_job", payload); state.runReport = null; state.planEdits.clear();
    renderPlans(state.planReport); renderResults(null);
    if (state.planReport.error) showError(`${state.planReport.error_code || "PLAN_ERROR"}: ${state.planReport.error}`);
  } catch (error) { showError(error.message); } finally { setLoading(false); }
}

let planSaveTimer = null;
let planSaveInFlight = false;
let planSaveDirty = false;

function schedulePlanSave() {
  setPlanSaveStatus("pending");
  clearTimeout(planSaveTimer);
  planSaveTimer = setTimeout(runPlanSave, 400);
  updateRunButton();
}

async function runPlanSave() {
  planSaveTimer = null;
  // Never run two saves at once; if edits arrived while one was in flight,
  // re-run after it finishes so the user never sees the awaiting-review race.
  if (planSaveInFlight) { planSaveDirty = true; return; }
  if (!state.planReport?.snapshot || !state.planReport?.job_id) return;
  const edits = Array.from(state.planEdits.values()).filter((edit) => !edit.pristine);
  if (!edits.length) { setPlanSaveStatus("idle"); return; }
  planSaveInFlight = true; state.planSaving = true; setPlanSaveStatus("saving"); updateRunButton();
  try {
    const payload = buildPayload();
    payload.job_id = state.planReport.job_id;
    payload.base_plan_id = state.planReport.snapshot.plan_id;
    payload.plan_edits = edits.map(({ pristine, ...edit }) => edit);
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
    if (membershipChanged) renderPlans(state.planReport);
    else renderPlanSummary(state.planReport);
    if (report.error) showError(`${report.error_code || "PLAN_ERROR"}: ${report.error}`);
  } catch (error) {
    setPlanSaveStatus("error", error.message);
  } finally {
    planSaveInFlight = false; state.planSaving = false;
    if (planSaveDirty) { planSaveDirty = false; runPlanSave(); }
    else { setPlanSaveStatus("saved"); updateRunButton(); }
  }
}

function setPlanSaveStatus(status, message = "") {
  const el = $("plan-save-status"); if (!el) return;
  el.dataset.status = status;
  el.textContent = status === "saving" ? t("plan.saving")
    : status === "saved" ? t("plan.saved")
    : status === "error" ? t("plan.saveError", { message })
    : "";
}

async function runMux() {
  clearError(); const payload = buildPayload();
  if (!state.planReport?.plans?.length || !state.planReport.snapshot) { showError(t("error.generatePlanFirst")); return; }
  if (state.planEdits.size && Array.from(state.planEdits.values()).some((edit) => !edit.pristine)) {
    clearTimeout(planSaveTimer); await runPlanSave();
  }
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

function buildPayload() {
  return { input_dir: $("input-dir").value.trim(), yes: false, overrides: {
    cleanup: getCustomSelectValue("cleanup"), extra_dir: $("extra-dir").value.trim(),
    output_suffix: $("output-suffix").value, output_dir: $("output-dir").value.trim(),
    name_strategy: getCustomSelectValue("name-strategy"), name_template: $("name-template").value.trim(),
    overwrite: $("overwrite").checked,
    font_mode: $("font-subset").checked ? "subset" : state.lastNonSubsetFontMode,
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

async function deleteAllJobs() {
  if (!state.jobs.length) return;
  if (await confirmAction(t("jobs.deleteAllConfirm"), { title: t("jobs.deleteAllTitle"), confirmLabel: t("jobs.deleteAll"), danger: true, review: false })) {
    try { await callApi("clear_jobs"); await loadJobs(); showToast(t("toast.jobsCleared.body", { count: state.jobs.length }), "success", t("toast.jobsCleared.title")); }
    catch (error) { showError(error.message); }
  }
}

async function previewJobDiagnostics(job) {
  state.currentDiagnosticsJobId = job.id;
  const dialog = $("diagnostics-dialog");
  const content = $("diagnostics-content");
  content.textContent = t("jobs.diagnostics.loading");
  dialog.returnValue = "";
  dialog.showModal();
  try {
    const result = await callApi("get_job_diagnostics", job.id);
    content.textContent = result.text;
  } catch (error) {
    content.textContent = error.message;
  }
}

async function exportDiagnosticsFromDialog() {
  const jobId = state.currentDiagnosticsJobId;
  const dialog = $("diagnostics-dialog");
  if (!jobId) return;
  dialog.querySelector("#diagnostics-export-btn").disabled = true;
  try {
    const result = await callApi("export_job_diagnostics", jobId);
    showToast(t("toast.diagnostics.body", { path: result.path }), "success", t("toast.diagnostics.title"), {
      label: t("toast.diagnostics.open"),
      callback: async () => { try { await callApi("open_diagnostics_location"); } catch (error) { showToast(error.message, "error", t("toast.environmentError.title")); } },
    }, 12000);
  } catch (error) { showError(error.message); }
  finally { dialog.querySelector("#diagnostics-export-btn").disabled = false; }
}

async function copyDiagnosticsFromDialog() {
  const text = $("diagnostics-content").textContent;
  try {
    await navigator.clipboard.writeText(text);
    showToast(t("jobs.diagnostics.copied"), "success", t("toast.diagnostics.title"));
  } catch (error) {
    showToast(error.message, "error", t("toast.environmentError.title"));
  }
}

async function callApi(method, payload) {
  if (!window.pywebview?.api?.[method]) throw new Error(t("error.bridgeUnavailable"));
  const response = payload === undefined ? await window.pywebview.api[method]() : await window.pywebview.api[method](payload);
  if (!response || response.ok !== true) throw new Error(response?.error || t("error.unknownApi"));
  return response.data;
}

function renderAppInfo() {
  if (!state.appInfo) return;
  setText("app-version", t("version", { version: state.appInfo.version }));
  setText("about-version", t("version", { version: state.appInfo.version }));
  setText("sidebar-config-path", state.appInfo.config_path || "");
}

async function openProjectLink(event) {
  const button = event.currentTarget;
  button.disabled = true;
  try { await callApi("open_project_link", button.dataset.projectLink); }
  catch (error) { showToast(error.message, "error", t("toast.linkError.title")); }
  finally { button.disabled = false; }
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
  if (resetDirty) state.dependencyDrafts = { mkvmerge: null, ffmpeg: null, unrar: null };
  ["mkvmerge", "ffmpeg", "unrar"].forEach(renderDependency);

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
  const cache = state.config.font_cache || {};
  if (resetDirty) {
    $("font-cache-enabled").checked = cache.enabled !== false;
    $("font-cache-max-size").value = cache.max_size_mb || 2048;
    $("font-cache-max-age").value = cache.max_age_days || 90;
    $("updates-enabled").checked = Boolean(state.config.updates?.enabled);
    $("plex-enabled").checked = Boolean(state.config.plex?.enabled);
    $("plex-server-url").value = state.config.plex?.server_url || "";
    $("plex-section-id").value = state.config.plex?.section_id || "";
    $("plex-token-env").value = state.config.plex?.token_env || "PLEXMUXY_PLEX_TOKEN";
    $("plex-path-mappings").value = (state.config.plex?.path_mappings || []).map((item) => `${item.local_root} = ${item.server_root}`).join("\n");
  }
  setText("update-check-status", state.config.updates?.enabled ? t("environment.updates.enabled") : t("environment.updates.disabled"));
  setText("plex-token-status", state.config.plex?.token_available ? t("environment.plex.tokenAvailable") : t("environment.plex.tokenMissing"));
  if (resetDirty) state.environmentDirty = false;
  updateRunButton();
}

function dependencyViewModel(name) {
  return state.dependencyDrafts[name] || state.config?.[name] || {};
}

function dependencyPathForSave(name) {
  const draft = state.dependencyDrafts[name];
  return String(draft ? draft.path : (state.config?.[name]?.configured_path || "")).trim();
}

function mapResultToDraft(result, origin) {
  return { ...result, path: result.path || result.resolved_path, resolved_path: result.path || result.resolved_path, origin, dirty: true, available: true, valid: true };
}

function setDependencyBusy(name, status) {
  if (status) state.dependencyBusy[name] = status; else delete state.dependencyBusy[name];
  renderDependency(name);
}

function renderDependency(name) {
  if (!state.config || !$(`${name}-status`)) return;
  const dependency = dependencyViewModel(name);
  const busy = state.dependencyBusy[name];
  const required = Boolean(state.config[name]?.required);
  const ready = Boolean(dependency.available && dependency.valid !== false);
  const status = busy || (ready ? "ready" : (required ? "required-missing" : "optional-missing"));
  const statusNode = $(`${name}-status`);
  const icons = { ready: "#icon-check", checking: "#icon-spinner", downloading: "#icon-download", "required-missing": "#icon-x", "optional-missing": "#icon-question", invalid: "#icon-x" };
  statusNode.querySelector("use")?.setAttribute("href", icons[status] || "#icon-x");
  statusNode.className = `dependency-state ${status}`;
  statusNode.setAttribute("aria-label", t(`environment.status.${status}`, { dependency: name }));
  const path = dependency.path || dependency.resolved_path || "";
  $(`${name}-path`).value = path;
  $(`${name}-source`).textContent = dependencySourceLabel(dependency.source);
  const draft = state.dependencyDrafts[name];
  const detailKey = draft ? `environment.pending.${draft.origin}` : (path ? (dependency.configured_path ? "environment.saved" : "environment.autoResolved") : (required ? "environment.requiredMissing" : "environment.optionalMissing"));
  $(`${name}-detail`).textContent = dependency.validation_error || t(detailKey);
  const versions = [];
  if (dependency.version) versions.push(t("environment.version", { version: dependency.version }));
  if (dependency.file_version) versions.push(t("environment.fileVersion", { version: dependency.file_version }));
  if (dependency.version_warning) versions.push(t("environment.versionMismatch"));
  $(`${name}-version`).textContent = versions.join(" · ");
  document.querySelectorAll(`[data-dependency="${name}"]`).forEach((button) => { button.disabled = Boolean(busy); });
  if (name === "unrar" && $("install-unrar-btn")) $("install-unrar-btn").disabled = Boolean(busy);
}

function dependencySourceLabel(source) {
  if (String(source).startsWith("environment:")) return t("environment.source.environment");
  if (String(source).startsWith("registry:")) return t("environment.source.registry");
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
  const tracks = state.config?.tracks || {};
  $("audio-filter-enabled").checked = Boolean(tracks.audio_filter_enabled);
  $("audio-exclude-patterns").value = (tracks.exclude_audio_title_patterns || []).join(", ");
  $("audio-keep-languages").value = (tracks.keep_audio_languages || []).join(", ");
  $("keep-default-audio").checked = tracks.keep_default_audio !== false;
  $("keep-unknown-audio").checked = tracks.keep_all_when_unknown !== false;
  $("allow-no-audio").checked = Boolean(tracks.allow_no_audio);
  state.settingsDirty = false; updateOptionAvailability(); updateRunButton();
}

function updateOptionAvailability() {
  const templateEnabled = getCustomSelectValue("name-strategy") === "template";
  if ($("name-template")) {
    $("name-template").disabled = !templateEnabled;
    $("name-template").setAttribute("aria-disabled", String(!templateEnabled));
  }
  const filterEnabled = Boolean($("audio-filter-enabled")?.checked);
  document.querySelectorAll(".audio-filter-option input").forEach((control) => {
    control.disabled = !filterEnabled;
    control.setAttribute("aria-disabled", String(!filterEnabled));
  });
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

function renderPlans(report) {
  const container = $("plans"); clear(container);
  state.planSaving = false;
  if (!report) {
    clearTimeout(planSaveTimer); planSaveInFlight = false; planSaveDirty = false; state.planSaving = false; state.planSaveError = null;
    clear($("plan-summary")); setPlanSaveStatus("idle"); state.planOrder = null; state.planData = null;
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
  const subsetPlans = report.plans.filter((plan) => plan.font_subset_intent?.summary);
  if (subsetPlans.length) {
    const familyCount = subsetPlans.reduce((total, plan) => total + Number(plan.font_subset_intent.summary.requested_family_count || 0), 0);
    const attachmentCount = subsetPlans.reduce((total, plan) => total + Number(plan.font_subset_intent.summary.expected_attachment_count || 0), 0);
    summary.append(badge(t("plan.subsetSummary", { families: familyCount, attachments: attachmentCount }), "info"));
  }
  setPlanSaveStatus("idle");
}

function dirnameOf(path) {
  const normalized = String(path).replace(/\\/g, "/");
  const idx = normalized.lastIndexOf("/");
  return idx <= 0 ? "" : normalized.slice(0, idx);
}

function basenameOf(path) {
  const normalized = String(path).replace(/\\/g, "/");
  const idx = normalized.lastIndexOf("/");
  return idx < 0 ? String(path) : normalized.slice(idx + 1);
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

  // Source folder + compact output name. When the output lands in the same
  // folder as the source, show only the output filename instead of the full path
  // (the directory is already implied by the source folder above).
  const sourceDir = dirnameOf(plan.source_video);
  const outputDir = dirnameOf(plan.output_path);
  const outputDisplay = sourceDir && outputDir === sourceDir ? basenameOf(plan.output_path) : plan.output_path;
  const meta = element("div", "plan-meta");
  if (sourceDir) meta.append(element("div", "file-path plan-source", t("plan.sourceFolder", { path: sourceDir })));
  meta.append(element("div", "file-path plan-output", t("plan.output", { path: outputDisplay })));
  article.append(meta);
  const grid = element("div", "track-grid");
  grid.append(
    renderSubtitleSection(plan),
    renderAudioSection(plan),
    trackBox(t("plan.fonts"), plan.attachments, (item) => document.createTextNode(item.name), t("plan.attachmentCount", { count: plan.attachments.length }), "attachments-box")
  );
  article.append(grid);
  article.append(renderAvailableAssignments(plan));
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

function currentPlanEdit(plan) {
  if (!state.planEdits.has(plan.source_video)) {
    state.planEdits.set(plan.source_video, {
      source_video: plan.source_video,
      revision: Number(plan.edit_revision || 0) + 1,
      enabled: true,
      included_subtitles: plan.subtitle_tracks.map((track) => track.path),
      included_external_audio: plan.audio_tracks.map((track) => track.path),
      source_track_overrides: [],
      subtitle_metadata_overrides: [],
      external_track_order: plan.external_track_order?.length ? [...plan.external_track_order] : [
        ...plan.subtitle_tracks.map((track) => `subtitle:${track.path}`),
        ...plan.audio_tracks.map((track) => `audio:${track.path}`),
      ],
      pristine: true,
    });
  }
  return state.planEdits.get(plan.source_video);
}

function markPlanEdited(cardEl) {
  if (cardEl) cardEl.classList.add("has-edits");
  else document.querySelectorAll(".plan-card").forEach((card) => card.classList.add("has-edits"));
}

function touchEdit(edit, cardEl) { delete edit.pristine; markPlanEdited(cardEl); schedulePlanSave(); }

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
      rebuildExternalOrder(edit);
      touchEdit(edit, li.closest(".plan-card"));
    });
    const copy = element("div", "source-track-copy");
    copy.append(badge(t("plan.audioExternal"), "info"), renderSubtitle(track));
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
      checkbox.addEventListener("change", () => updateSubtitleOverride(edit, track, field, checkbox.checked, li.closest(".plan-card")));
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
      edit.source_track_overrides = edit.source_track_overrides.filter((item) => item.track_id !== track.id);
      edit.source_track_overrides.push({ track_id: track.id, included: input.checked });
      touchEdit(edit, li.closest(".plan-card"));
    });
    const copy = element("div", "source-track-copy");
    copy.append(
      badge(t("plan.audioSource"), "ok"),
      element("strong", "", `${track.id} · ${track.title || t("plan.unknownTitle")}`),
      element("span", "file-path", track.language || t("plan.unknownLanguage")),
      element("span", "decision-reason", localizeEnum("track.reason", track.decision_reason))
    );
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
  handle.innerHTML = '<svg viewBox="0 0 10 16" width="10" height="16" fill="currentColor" aria-hidden="true"><circle cx="2.5" cy="3" r="1.5"/><circle cx="2.5" cy="8" r="1.5"/><circle cx="2.5" cy="13" r="1.5"/><circle cx="7.5" cy="3" r="1.5"/><circle cx="7.5" cy="8" r="1.5"/><circle cx="7.5" cy="13" r="1.5"/></svg>';
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
  override[field] = value; delete edit.pristine;
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
      edit.source_track_overrides = edit.source_track_overrides.filter((item) => item.track_id !== track.id);
      edit.source_track_overrides.push({ track_id: track.id, included: input.checked });
      touchEdit(edit, li.closest(".plan-card"));
    });
    const copy = element("div", "source-track-copy");
    copy.append(
      badge(t("plan.audioSource"), "ok"),
      element("strong", "", `${track.id} · ${track.title || t("plan.unknownTitle")}`),
      element("span", "file-path", `${track.codec || "?"} / ${track.language || t("plan.unknownLanguage")} / ${track.channels || "?"}ch`),
      element("span", "decision-reason", localizeEnum("track.reason", track.decision_reason))
    );
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

function renderAvailableAssignments(plan) {
  const details = element("details", "source-track-panel assignment-panel");
  details.append(element("summary", "", t("plan.assignments")));
  const edit = currentPlanEdit(plan); const list = element("div", "assignment-list");
  const groups = [
    ["subtitle", state.planReport?.available_subtitles || [], "included_subtitles"],
    ["audio", state.planReport?.available_audio || [], "included_external_audio"],
  ];
  groups.forEach(([kind, candidates, field]) => candidates.forEach((candidate) => {
    if ((kind === "subtitle" ? plan.subtitle_tracks : plan.audio_tracks).some((track) => track.path === candidate.path)) return;
    const row = element("div", "source-track-row"); const copy = itemNode(candidate.name, candidate.path);
    const button = element("button", "ghost compact"); button.type = "button";
    const sync = () => { button.textContent = edit[field].includes(candidate.path) ? t("plan.unassign") : t("plan.assign"); };
    button.addEventListener("click", () => {
      edit[field] = edit[field].includes(candidate.path)
        ? edit[field].filter((path) => path !== candidate.path)
        : [...edit[field], candidate.path];
      rebuildExternalOrder(edit);
      touchEdit(edit, row.closest(".plan-card")); sync();
    });
    sync(); row.append(copy, button); list.append(row);
  }));
  if (!list.childNodes.length) list.append(element("div", "file-path", t("plan.noAssignments")));
  details.append(list); return details;
}

function rebuildExternalOrder(edit) {
  edit.external_track_order = [
    ...edit.included_subtitles.map((path) => `subtitle:${path}`),
    ...edit.included_external_audio.map((path) => `audio:${path}`),
  ];
}

function renderSubtitle(track) {
  const wrapper = element("div"); const flags = [track.default_track ? t("track.default") : "", track.forced_track ? t("track.forced") : ""].filter(Boolean);
  wrapper.append(document.createTextNode(`${track.name}${flags.length ? ` (${flags.join(", ")})` : ""}`));
  wrapper.append(element("div", "file-path", `${track.track_name} / ${track.mkv_language} / ${track.ietf_language}`), element("div", "file-path", track.match_reason)); return wrapper;
}
function renderAudio(track) { return itemNode(track.name, track.match_reason); }
function itemNode(text, detail) { const node = element("div", "", text); if (detail) node.append(element("div", "file-path", detail)); return node; }

function boxHeader(title, countText) {
  const head = element("h5", "", title);
  if (countText) head.append(badge(countText, "info"));
  return head;
}

function trackBox(title, items, renderer, countText, boxClass) {
  const box = element("div", "track-box" + (boxClass ? " " + boxClass : "")); box.append(boxHeader(title, countText));
  if (!items?.length) { box.append(element("div", "file-path", t("plan.none"))); return box; }
  const list = element("ul", "item-list"); items.forEach((item) => { const li = element("li"); li.append(renderer(item)); list.append(li); }); box.append(list); return box;
}

function renderSkippedFiles(skipped, title) { return trackBox(title, skipped, (item) => itemNode(item.name, `${item.reason} / ${item.stage}`)); }

// Minimal fallback for a disabled plan whose full data is not cached (rare);
// the normal path renders a disabled plan as a full in-place card instead.
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
  delete edit.pristine;
  markPlanEdited(null);
  schedulePlanSave();
}

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
function showError(message) {
  showToast(message, "error", t("error.title"), null, 9000);
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
