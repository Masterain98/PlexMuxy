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
    persistPreference({ theme: mode });
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


