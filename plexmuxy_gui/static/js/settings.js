function persistPreference(payload) {
  if (!window.pywebview?.api?.save_preferences) return;
  callApi("save_preferences", payload).catch(() => { /* Preference persistence is best-effort. */ });
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



async function chooseDirectory() {
  clearError();
  try {
    const result = await callApi("choose_directory");
    if (!result.cancelled && result.path) { state.inputDir = result.path; $("input-dir").value = result.path; clearReports(); }
  } catch (error) { showError(error.message); }
}

async function chooseOutputDirectory() {
  clearError();
  try {
    const result = await callApi("choose_directory");
    if (!result.cancelled && result.path) { $("output-dir").value = result.path; handleOverrideChange(); }
  } catch (error) { showError(error.message); }
}

function resetExtraDirToRecommended() {
  $("extra-dir").value = "Extra";
  handleOverrideChange();
}

function resetOutputDirToRecommended() {
  $("output-dir").value = "";
  handleOverrideChange();
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

// --- Manual plan-edit saving (no auto-save) ---------------------------------
// Edits are held in memory and only persisted when the user clicks the floating
// "Save" button. A per-edit baseline (a snapshot of the original plan-derived
// values) lets us count *actual* changes, so reverting a setting back to its
// original value decrements the unsaved-change counter.



function renderAppInfo() {
  if (!state.appInfo) return;
  setText("app-version", t("version", { version: state.appInfo.version }));
  setText("about-version", t("version", { version: state.appInfo.version }));
  setText("sidebar-config-path", state.appInfo.config_path || "");
  // Reveal the edge resize handles only where the frameless window can resize.
  if (document.body) {
    document.body.classList.toggle("frame-resizable", Boolean(state.appInfo.resizable_frame));
  }
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
  if (resetDirty) {
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
  const mkvmergeVersion = state.config?.mkvmerge?.version;
  const autoMime = autoPickFontMimeMode(mkvmergeVersion);
  const configMime = state.config?.font?.mime_mode;
  setCustomSelectValue("font-mime-mode", configMime || autoMime);
  setCustomSelectValue("font-embed-scheme", state.config?.font?.embed_scheme || "attachment");
  updateFontMimeRecommendation(mkvmergeVersion);
  const tracks = state.config?.tracks || {};
  $("audio-filter-enabled").checked = Boolean(tracks.audio_filter_enabled);
  $("audio-exclude-patterns").value = (tracks.exclude_audio_title_patterns || []).join(", ");
  $("audio-keep-languages").value = (tracks.keep_audio_languages || []).join(", ");
  $("keep-default-audio").checked = tracks.keep_default_audio !== false;
  $("keep-unknown-audio").checked = tracks.keep_all_when_unknown !== false;
  $("allow-no-audio").checked = Boolean(tracks.allow_no_audio);
  state.settingsDirty = false; updateOptionAvailability(); updateRunButton();
}

function autoPickFontMimeMode(versionString) {
  if (!versionString) return "legacy";
  const match = String(versionString).match(/v?(\d+)/);
  if (!match) return "legacy";
  const major = parseInt(match[1], 10);
  return major >= 66 ? "modern" : "legacy";
}

function updateFontMimeRecommendation(versionString) {
  const recommended = autoPickFontMimeMode(versionString);
  const listbox = $("font-mime-mode-listbox");
  if (!listbox) return;
  const options = listbox.querySelectorAll('[role="option"]');
  options.forEach((option) => {
    // Remove existing recommendation badge text
    const baseText = (option.dataset.i18nOriginalText || option.textContent).replace(/\s*（推荐）$/, "").replace(/\s*\(Recommended\)$/, "");
    option.dataset.i18nOriginalText = baseText;
    if (option.dataset.value === recommended) {
      option.textContent = baseText + " " + t("options.fontMimeMode.recommended");
    } else {
      option.textContent = baseText;
    }
  });
  // Also update the trigger label to include the badge for the currently selected option
  syncCustomSelectLabels();
  // Apply the recommendation to the trigger label after sync
  const trigger = $("font-mime-mode");
  if (!trigger) return;
  const selectedValue = trigger.dataset.value;
  if (selectedValue === recommended) {
    const label = trigger.querySelector("[data-select-label]");
    if (label) {
      const base = label.textContent.replace(/\s*（推荐）$/, "").replace(/\s*\(Recommended\)$/, "");
      label.textContent = base + " " + t("options.fontMimeMode.recommended");
    }
  }
}

// Hook into custom select changes for font-mime-mode to update recommendation badge on trigger
function handleFontMimeModeChange() {
  handleOverrideChange();
  const mkvmergeVersion = state.config?.mkvmerge?.version;
  updateFontMimeRecommendation(mkvmergeVersion);
}



function updateOptionAvailability() {
  const strategy = getCustomSelectValue("name-strategy");
  const suffixRow = $("output-suffix-row");
  const templateRow = $("name-template-row");

  if (suffixRow) {
    if (strategy === "suffix") {
      showCollapsibleRow(suffixRow);
    } else {
      hideCollapsibleRow(suffixRow);
    }
  }
  if (templateRow) {
    if (strategy === "template") {
      showCollapsibleRow(templateRow);
    } else {
      hideCollapsibleRow(templateRow);
    }
  }

  const filterEnabled = Boolean($("audio-filter-enabled")?.checked);
  document.querySelectorAll(".audio-filter-option.option-collapsible").forEach((row) => {
    if (filterEnabled) {
      showCollapsibleRow(row);
    } else {
      hideCollapsibleRow(row);
    }
  });

  applyCompatibility();
}

function showCollapsibleRow(row) {
  if (!row) return;
  // Invalidate any pending hide transitions
  row._hideGen = (row._hideGen || 0) + 1;
  // Remove inline display:none so CSS grid takes over for the transition
  row.style.display = "";
  // Force reflow before removing is-hidden so transition fires
  void row.offsetHeight;
  row.classList.remove("is-hidden");
  // Re-enable all inputs inside
  row.querySelectorAll("input, button, select, textarea").forEach((el) => {
    el.disabled = false;
    el.setAttribute("aria-disabled", "false");
  });
}

function hideCollapsibleRow(row) {
  if (!row) return;
  row.classList.add("is-hidden");
  // Track generation to discard stale transitionend events
  const gen = (row._hideGen || 0) + 1;
  row._hideGen = gen;
  const onTransitionEnd = () => {
    if (row._hideGen !== gen) return;
    if (row.classList.contains("is-hidden")) {
      row.style.display = "none";
    }
    row.removeEventListener("transitionend", onTransitionEnd);
  };
  row.addEventListener("transitionend", onTransitionEnd);
  // Disable all inputs inside
  row.querySelectorAll("input, button, select, textarea").forEach((el) => {
    el.disabled = true;
    el.setAttribute("aria-disabled", "true");
  });
}

// Enable/disable settings based on the environment compatibility report
// (state.config.compatibility) produced by the backend. Every element carrying a
// data-compat="<setting id>" attribute is toggled according to whether its
// declared tool-version requirements are satisfied.


function applyCompatibility() {
  const report = state.config?.compatibility || {};
  document.querySelectorAll("[data-compat]").forEach((element) => {
    const info = report[element.dataset.compat];
    const blocked = Boolean(info) && info.satisfied === false;
    const isOption = element.getAttribute("role") === "option";
    const control = isOption ? element : element.querySelector('[role="combobox"]') || element;
    if ("disabled" in control) control.disabled = blocked;
    element.setAttribute("aria-disabled", String(blocked));
    element.classList.toggle("is-unavailable", blocked);
    if (blocked) {
      const requirement = (info.unmet_describe || info.unmet || []).join(", ");
      element.title = requirement ? t("compatibility.requires", { requirement }) : "";
    } else {
      element.removeAttribute("title");
    }
    if (blocked && isOption && element.getAttribute("aria-selected") === "true") {
      const root = element.closest("[data-custom-select]");
      const trigger = root?.querySelector('[role="combobox"]');
      const fallback = customSelectOptions(root).find((option) => !isCustomOptionDisabled(option));
      if (trigger && fallback) setCustomSelectValue(trigger.id, fallback.dataset.value, false);
    }
  });
}


