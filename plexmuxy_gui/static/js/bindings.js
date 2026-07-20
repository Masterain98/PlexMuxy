function bindEvents() {
  const bindings = [
    ["window-minimize-btn", "click", minimizeWindow], ["window-maximize-btn", "click", toggleMaximizeWindow],
    ["window-close-btn", "click", closeWindow], ["window-drag-region", "dblclick", toggleMaximizeWindow],
    ["sidebar-toggle", "click", toggleSidebar], ["sidebar-scrim", "click", closeSidebar],
    ["skip-link", "click", skipToMainContent],
    ["alert-close-btn", "click", clearError],
    ["choose-dir-btn", "click", chooseDirectory], ["open-config-btn", "click", openConfigLocation],
    ["output-dir-choose-btn", "click", chooseOutputDirectory],
    ["output-dir-recommended-btn", "click", resetOutputDirToRecommended],
    ["extra-dir-choose-btn", "click", chooseExtraDirectory],
    ["extra-dir-recommended-btn", "click", resetExtraDirToRecommended],
    ["diagnostics-btn", "click", exportDiagnostics], ["save-settings-btn", "click", saveSettings],
    ["save-environment-btn", "click", saveEnvironmentSettings], ["test-notification-btn", "click", testNotification],
    ["plan-btn", "click", generatePlan], ["run-btn", "click", runMux], ["cancel-btn", "click", cancelJob],
    ["plan-save-fab", "click", savePlanEdits],
    ["refresh-jobs-btn", "click", loadJobs],
    ["queue-toggle-btn", "click", toggleQueue],
    ["delete-all-jobs-btn", "click", deleteAllJobs],
    ["diagnostics-export-btn", "click", exportDiagnosticsFromDialog],
    ["diagnostics-copy-btn", "click", copyDiagnosticsFromDialog],
    ["check-updates-btn", "click", checkUpdates],
    ["input-dir", "input", (event) => { state.inputDir = event.target.value; clearReports(); }],
    ["cleanup", "change", handleOverrideChange], ["extra-dir", "input", handleOverrideChange],
    ["output-suffix", "input", handleOverrideChange], ["output-dir", "input", handleOverrideChange],
    ["name-strategy", "change", handleOverrideChange], ["name-template", "input", handleOverrideChange],
    ["overwrite", "change", handleOverrideChange], ["font-subset", "change", handleFontSubsetChange],
    ["font-mime-mode", "change", handleFontMimeModeChange],
    ["audio-filter-enabled", "change", handleOverrideChange],
    ["audio-exclude-patterns", "input", handleOverrideChange], ["audio-keep-languages", "input", handleOverrideChange],
    ["keep-default-audio", "change", handleOverrideChange], ["keep-unknown-audio", "change", handleOverrideChange],
    ["allow-no-audio", "change", handleOverrideChange],
    ["notifications-enabled", "change", persistNotificationSetting],
    ["updates-enabled", "change", handleEnvironmentChange],
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
  document.querySelectorAll(".resize-handle").forEach((handle) => {
    if (!handle.dataset.boundPointer) {
      handle.addEventListener("pointerdown", startWindowResize);
      handle.addEventListener("pointermove", moveWindowResize);
      handle.addEventListener("pointerup", endWindowResize);
      handle.addEventListener("pointercancel", endWindowResize);
      handle.dataset.boundPointer = "true";
    }
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


