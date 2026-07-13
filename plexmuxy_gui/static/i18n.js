(() => {
  "use strict";

  const STORAGE_KEY = "plexmuxy-locale";
  const DEFAULT_LOCALE = "en";
  const LOCALES = Object.freeze({
    en: Object.freeze({ file: "./locales/en.json", labelKey: "language.english" }),
    "zh-CN": Object.freeze({ file: "./locales/zh-CN.json", labelKey: "language.chinese" })
  });
  const SUPPORTED_LOCALES = Object.freeze(Object.keys(LOCALES));
  const SUPPORTED_MODES = Object.freeze(["system", ...SUPPORTED_LOCALES]);
  const catalogs = new Map();
  const missingKeys = new Set();

  let mode = "system";
  let locale = DEFAULT_LOCALE;
  let readyPromise = null;

  function normalizeLocale(value) {
    const normalized = String(value || "").replace("_", "-").toLowerCase();
    if (normalized === "zh" || normalized.startsWith("zh-cn") || normalized.startsWith("zh-hans") || normalized.startsWith("zh-sg")) return "zh-CN";
    return DEFAULT_LOCALE;
  }

  function resolveLocale(selectedMode) {
    return selectedMode === "system" ? normalizeLocale(navigator.languages?.[0] || navigator.language) : normalizeLocale(selectedMode);
  }

  function interpolate(template, variables) {
    return String(template).replace(/\{([\w-]+)\}/g, (match, key) => Object.prototype.hasOwnProperty.call(variables, key) ? String(variables[key]) : match);
  }

  function reportMissingKey(key) {
    if (missingKeys.has(key)) return;
    missingKeys.add(key);
    console.warn(`[i18n] Missing translation key: ${key}`);
  }

  function t(key, variables = {}) {
    const localized = catalogs.get(locale)?.[key];
    const template = localized === "" || localized === undefined ? catalogs.get(DEFAULT_LOCALE)?.[key] : localized;
    if (template === undefined) {
      reportMissingKey(key);
      return key;
    }
    return interpolate(template, variables);
  }

  function validateCatalog(candidate, catalogLocale) {
    if (!candidate || Array.isArray(candidate) || typeof candidate !== "object") throw new Error(`Locale ${catalogLocale} must contain a JSON object.`);
    const invalidKey = Object.keys(candidate).find((key) => typeof candidate[key] !== "string");
    if (invalidKey) throw new Error(`Locale ${catalogLocale} has a non-string value at ${invalidKey}.`);
    return Object.freeze({ ...candidate });
  }

  async function loadCatalog(catalogLocale) {
    if (catalogs.has(catalogLocale)) return catalogs.get(catalogLocale);
    const descriptor = LOCALES[catalogLocale];
    if (!descriptor) throw new Error(`Unsupported locale: ${catalogLocale}`);
    const response = await fetch(new URL(descriptor.file, document.baseURI), { cache: "no-cache" });
    if (!response.ok && response.status !== 0) throw new Error(`Could not load ${descriptor.file} (${response.status}).`);
    const catalog = validateCatalog(await response.json(), catalogLocale);
    catalogs.set(catalogLocale, catalog);
    return catalog;
  }

  function applyDocument(root = document) {
    document.documentElement.lang = locale;
    document.documentElement.dataset.locale = locale;
    document.documentElement.dataset.localeMode = mode;
    document.title = t("meta.title");

    root.querySelectorAll("[data-i18n]").forEach((node) => { node.textContent = t(node.dataset.i18n); });
    ["title", "aria-label", "placeholder", "content"].forEach((attribute) => {
      const datasetKey = "i18n" + attribute.split("-").map((part) => part[0].toUpperCase() + part.slice(1)).join("");
      root.querySelectorAll(`[data-${datasetKey.replace(/[A-Z]/g, (letter) => "-" + letter.toLowerCase())}]`).forEach((node) => {
        node.setAttribute(attribute, t(node.dataset[datasetKey]));
      });
    });
  }

  function readStoredMode() {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (SUPPORTED_MODES.includes(saved)) return saved;
    } catch (_) {
      // Hardened webviews may disable storage; system language remains a safe default.
    }
    return "system";
  }

  async function initialize() {
    if (readyPromise) return readyPromise;
    mode = readStoredMode();
    locale = resolveLocale(mode);
    readyPromise = (async () => {
      try {
        await loadCatalog(DEFAULT_LOCALE);
        if (locale !== DEFAULT_LOCALE) {
          try { await loadCatalog(locale); }
          catch (error) { console.error("[i18n] Falling back to English.", error); locale = DEFAULT_LOCALE; }
        }
        applyDocument();
      } catch (error) {
        locale = DEFAULT_LOCALE;
        document.documentElement.lang = locale;
        document.documentElement.dataset.locale = locale;
        console.error("[i18n] Could not load the source language. Static English text will be used.", error);
      } finally {
        document.documentElement.dataset.i18nReady = "true";
      }
    })();
    return readyPromise;
  }

  async function setLocale(nextMode) {
    await initialize();
    mode = SUPPORTED_MODES.includes(nextMode) ? nextMode : "system";
    const requestedLocale = resolveLocale(mode);
    let usedFallback = false;
    try {
      await loadCatalog(requestedLocale);
      locale = requestedLocale;
    } catch (error) {
      console.error(`[i18n] Could not load ${requestedLocale}; falling back to English.`, error);
      locale = DEFAULT_LOCALE;
      usedFallback = true;
    }
    try { localStorage.setItem(STORAGE_KEY, mode); } catch (_) { /* Keep the in-memory choice. */ }
    applyDocument();
    window.dispatchEvent(new CustomEvent("plexmuxy:localechange", { detail: { mode, locale, requestedLocale, usedFallback } }));
    return { mode, locale, requestedLocale, usedFallback };
  }

  window.PlexMuxyI18n = Object.freeze({
    applyDocument,
    getLocale: () => locale,
    getMode: () => mode,
    getSupportedLocales: () => SUPPORTED_LOCALES.map((code) => ({ code, ...LOCALES[code] })),
    initialize,
    loadCatalog,
    setLocale,
    t,
    whenReady: initialize
  });

  initialize();
})();
