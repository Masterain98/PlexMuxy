function closeSiblingMenus(event) {
  if (!event.currentTarget.open) return;
  document.querySelectorAll(".theme-menu[open]").forEach((menu) => {
    if (menu !== event.currentTarget) menu.open = false;
  });
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
  if (isCustomOptionDisabled(option)) { closeCustomSelect(root, restoreFocus); return; }
  const trigger = root.querySelector('[role="combobox"]');
  setCustomSelectValue(trigger.id, option.dataset.value, emitChange);
  closeCustomSelect(root, restoreFocus);
}



function isCustomOptionDisabled(option) {
  return Boolean(option?.disabled) || option?.getAttribute("aria-disabled") === "true";
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


