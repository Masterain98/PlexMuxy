const state = {
  appInfo: null, config: null, inputDir: "", planReport: null,
  runReport: null, loading: false, activeJobId: null, windowMaximized: false,
  settingsDirty: false, environmentDirty: false, themeMode: "system", systemThemeQuery: null, navigationObserver: null,
  navigationTarget: null, navigationScrollCleanup: null, localeMode: "system",
  loadingMessageKey: "loading.initializing", lastJobStatus: null, currentView: "workspace",
  routed: false, lastHandledRoute: "",
  lastNonSubsetFontMode: "all",
  planEdits: new Map(), jobs: [], queuePaused: false, activePreviewId: null,
  planSaving: false,
  planOrder: null, planData: null, collapsedCards: new Set(),
  dependencyDrafts: { mkvmerge: null, ffmpeg: null, unrar: null }, dependencyBusy: {},
  currentDiagnosticsJobId: null,
};

const THEME_STORAGE_KEY = "plexmuxy-theme";
const selectSearch = new WeakMap();

const $ = (id) => document.getElementById(id);
const t = (key, variables = {}) => window.PlexMuxyI18n?.t(key, variables) ?? key;
