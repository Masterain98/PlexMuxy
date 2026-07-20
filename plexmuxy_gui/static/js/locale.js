async function initializeLocaleControls() {
  if (!window.PlexMuxyI18n) return;
  await window.PlexMuxyI18n.initialize();
  state.localeMode = window.PlexMuxyI18n.getMode();
  syncLocaleControls();
  syncCustomTooltips();
}



async function chooseLocale(event) {
  const mode = event.currentTarget.dataset.localeMode;
  await window.PlexMuxyI18n?.setLocale(mode);
  persistPreference({ locale: mode });
  const menu = $("language-menu");
  if (menu) menu.open = false;
}

// Persist appearance/language choices through the Python backend so they survive
// restarts. pywebview's http_server binds a random port each launch, which
// changes the page origin and makes localStorage (isolated per-origin)
// unreliable for cross-session persistence; the backend file is authoritative.


async function syncPreferencesFromBackend() {
  if (!window.pywebview?.api?.get_preferences) return;
  let preferences;
  try { preferences = await callApi("get_preferences"); }
  catch (_) { return; }
  if (!preferences) return;

  if (["system", "light", "dark"].includes(preferences.theme) && preferences.theme !== state.themeMode) {
    applyTheme(preferences.theme, false);
  }
  try { localStorage.setItem(THEME_STORAGE_KEY, state.themeMode); } catch (_) { /* Cache is optional. */ }

  const currentLocaleMode = window.PlexMuxyI18n?.getMode();
  if (window.PlexMuxyI18n && ["system", "en", "zh-CN", "zh-TW", "ru"].includes(preferences.locale) && preferences.locale !== currentLocaleMode) {
    await window.PlexMuxyI18n.setLocale(preferences.locale);
  }
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
  renderJobs();
  if (state.lastJobStatus) renderProgress(state.lastJobStatus);
  if (state.loading) setText("loading-text", t(state.loadingMessageKey));
  if (state.activeJobId) setRuntimeStatus(t("status.jobRunning"));
  updateRouteLabels();
  if (state.config?.mkvmerge?.version && typeof updateFontMimeRecommendation === "function") {
    updateFontMimeRecommendation(state.config.mkvmerge.version);
  }
}



function syncCustomTooltips() {
  document.querySelectorAll("[data-i18n-title]").forEach((node) => {
    node.dataset.tooltip = t(node.dataset.i18nTitle);
    node.removeAttribute("title");
  });
}


