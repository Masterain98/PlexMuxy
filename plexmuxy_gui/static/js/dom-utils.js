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



function itemNode(text, detail) { const node = element("div", "", text); if (detail) node.append(element("div", "file-path", detail)); return node; }
// Renders one metadata value on its own line with a localized label prefix so
// users can tell what each value means (e.g. "MKV language: chi"). Returns null
// when the value is empty so callers can skip it.


function metaRow(labelKey, value) {
  if (value === null || value === undefined || value === "") return null;
  const row = element("div", "track-meta-row");
  row.append(element("span", "track-meta-label", t(labelKey)));
  row.append(element("span", "track-meta-value", String(value)));
  return row;
}


function appendMetaRows(container, rows) { rows.forEach((node) => { if (node) container.append(node); }); }



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



function element(tag, className = "", text = null) { const node = document.createElement(tag); if (className) node.className = className; if (text !== null) node.textContent = String(text); return node; }


function iconSvg(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "icon");
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", `#${name}`);
  svg.appendChild(use);
  return svg;
}


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

