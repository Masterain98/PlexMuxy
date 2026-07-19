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



async function openProjectLink(event) {
  const button = event.currentTarget;
  button.disabled = true;
  try { await callApi("open_project_link", button.dataset.projectLink); }
  catch (error) { showToast(error.message, "error", t("toast.linkError.title")); }
  finally { button.disabled = false; }
}


