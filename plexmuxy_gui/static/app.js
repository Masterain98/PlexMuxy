window.PlexMuxyRequestClose = closeWindow;

window.addEventListener("pywebviewready", async () => {
  await initializeLocaleControls();
  bindEvents();
  initializeCustomSelects();
  initializeTheme();
  await syncPreferencesFromBackend();
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


