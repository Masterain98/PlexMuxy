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



function startWindowResize(event) {
  const handle = event.currentTarget;
  const direction = handle.dataset.resize;
  if (!direction) return;
  event.preventDefault();
  event.stopPropagation();
  try {
    callApi("resize_window", direction)
      .then((result) => {
        // If the resize began from a maximized window, the backend restores it
        // first; mirror that on the maximize button so its state stays correct.
        if (result && typeof result.maximized === "boolean" && !result.maximized) {
          const button = $("window-maximize-btn");
          if (button) {
            button.classList.remove("is-maximized");
            button.setAttribute("aria-pressed", "false");
            button.setAttribute("aria-label", t("window.maximize"));
            button.dataset.tooltip = t("window.maximizeShort");
            button.removeAttribute("title");
          }
        }
      })
      .catch((error) => showError(error.message));
  } catch (error) {
    showError(error.message);
  }
}


