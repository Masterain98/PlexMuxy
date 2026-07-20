function skipToMainContent(event) {
  event.preventDefault();
  $("main-content")?.focus({ preventScroll: true });
}



function initializeNavigation() {
  syncSidebarAccessibility();
  if (state.navigationObserver || !$("main-content")) { handleRoute(false); return; }
  const links = Array.from(document.querySelectorAll('.steps .step[data-route="workspace"]'));
  const sections = links.map((link) => $(link.dataset.section)).filter(Boolean);
  sections.sort((left, right) => left.offsetTop - right.offsetTop);
  const updateActiveSection = () => {
    if (state.navigationTarget) { setActiveNavigation(state.navigationTarget); return; }
    if (state.currentView !== "workspace") return;
    const main = $("main-content"); const rootTop = main.getBoundingClientRect().top;
    let current = sections[0];
    sections.forEach((section) => {
      if (section.getBoundingClientRect().top <= rootTop + 120) current = section;
    });
    if (main.scrollTop + main.clientHeight >= main.scrollHeight - 8) current = sections[sections.length - 1];
    if (current) setActiveNavigation(`#/workspace/${current.id}`);
  };
  state.navigationObserver = new IntersectionObserver(() => {
    updateActiveSection();
  }, { root: $("main-content"), rootMargin: "-12% 0px -72% 0px", threshold: [0, 0.05] });
  sections.forEach((section) => state.navigationObserver.observe(section));
  $("app-shell").scrollTop = 0;
  handleRoute(false);
}



function handleNavigationClick(event) {
  event.preventDefault();
  const target = event.currentTarget.getAttribute("href");
  window.history.replaceState(null, "", target);
  handleRoute(true);
  closeSidebar(false);
}



function parseRoute(hash = window.location.hash) {
  const normalized = String(hash || "").replace(/^#\/?/, "");
  const parts = normalized.split("/").filter(Boolean);
  if (parts[0] === "environment") return { view: "environment", section: null };
  if (parts[0] === "jobs") return { view: "jobs", section: null };
  if (parts[0] === "about") return { view: "about", section: null };
  if (parts[0] === "workspace") return { view: "workspace", section: parts[1] || "directory-section" };
  if (normalized && $(normalized)) return { view: "workspace", section: normalized };
  return { view: "workspace", section: "directory-section" };
}



function handleRoute(smooth = false) {
  const route = parseRoute();
  const routeKey = route.view + (route.view === "workspace" ? `:${$(route.section) ? route.section : "directory-section"}` : "");
  const firstRoute = !state.routed;
  const routeChanged = routeKey !== state.lastHandledRoute;
  state.routed = true;
  state.lastHandledRoute = routeKey;
  state.currentView = route.view;
  const workspace = $("workspace-view"); const environment = $("environment-view"); const jobs = $("jobs-view"); const about = $("about-view");
  const showWorkspace = route.view === "workspace";
  workspace?.classList.toggle("hidden", !showWorkspace);
  environment?.classList.toggle("hidden", route.view !== "environment");
  jobs?.classList.toggle("hidden", route.view !== "jobs");
  about?.classList.toggle("hidden", route.view !== "about");
  if (workspace) workspace.inert = !showWorkspace;
  if (environment) environment.inert = route.view !== "environment";
  if (jobs) jobs.inert = route.view !== "jobs";
  if (about) about.inert = route.view !== "about";
  updateRouteLabels();
  if (showWorkspace) {
    const section = $(route.section) ? route.section : "directory-section";
    const target = `#\/workspace/${section}`;
    setActiveNavigation(target);
    // On the very first load of the default (top) section, stay at the top of
    // the page so the intro header is visible. Otherwise only scroll when the
    // route actually changes or this is an explicit navigation, so redundant
    // re-initialization (DOMContentLoaded + pywebviewready) does not nudge the
    // scroll position away from the top.
    if (firstRoute && section === "directory-section") {
      $("app-shell").scrollTop = 0;
      $("main-content")?.scrollTo({ top: 0, behavior: "auto" });
    } else if (routeChanged || smooth) {
      window.setTimeout(() => scrollToSection(`#${section}`, smooth), 0);
    }
  } else if (route.view === "environment") {
    state.navigationScrollCleanup?.();
    state.navigationTarget = null;
    setActiveNavigation("#/environment");
  } else if (route.view === "jobs") {
    state.navigationScrollCleanup?.(); state.navigationTarget = null; setActiveNavigation("#/jobs"); loadJobs();
    $("main-content")?.scrollTo({ top: 0, behavior: "auto" });
  } else {
    state.navigationScrollCleanup?.(); state.navigationTarget = null; setActiveNavigation("#/about");
    $("main-content")?.scrollTo({ top: 0, behavior: "auto" });
  }
}



function updateRouteLabels() {
  const environment = state.currentView === "environment";
  const jobs = state.currentView === "jobs";
  const about = state.currentView === "about";
  setText("topbar-context", environment ? t("topbar.system") : jobs ? t("sidebar.jobs.title") : about ? t("topbar.application") : t("topbar.workspace"));
  setText("topbar-page", environment ? t("sidebar.environment.title") : jobs ? t("jobs.title") : about ? t("sidebar.about.title") : t("topbar.newJob"));
  document.title = environment ? t("document.environmentTitle") : jobs ? t("jobs.title") : about ? t("document.aboutTitle") : t("document.workspaceTitle");
}



function scrollToSection(targetSelector, smooth) {
  const main = $("main-content"); const target = document.querySelector(targetSelector);
  if (!main || !target) return;
  const navigationKey = `#/workspace/${target.id}`;
  state.navigationScrollCleanup?.();
  state.navigationTarget = navigationKey;
  setActiveNavigation(navigationKey);
  $("app-shell").scrollTop = 0;
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const useSmoothScroll = smooth && !reducedMotion;
  const targetTop = () => Math.max(0, main.scrollTop + target.getBoundingClientRect().top - main.getBoundingClientRect().top - 24);
  let settleTimer = null;
  const releaseNavigationLock = () => {
    if (settleTimer) window.clearTimeout(settleTimer);
    main.removeEventListener("scroll", handleProgrammaticScroll);
    if (state.navigationTarget === navigationKey) {
      state.navigationTarget = null;
      setActiveNavigation(navigationKey);
    }
    if (state.navigationScrollCleanup === releaseNavigationLock) state.navigationScrollCleanup = null;
  };
  const handleProgrammaticScroll = () => {
    if (settleTimer) window.clearTimeout(settleTimer);
    settleTimer = window.setTimeout(releaseNavigationLock, 140);
  };
  state.navigationScrollCleanup = releaseNavigationLock;
  if (!useSmoothScroll) {
    main.scrollTo({ top: targetTop(), behavior: "auto" });
    window.requestAnimationFrame(releaseNavigationLock);
    return;
  }
  // Drive the smooth scroll ourselves so the destination is re-measured on every
  // frame. Otherwise the native smooth scroll commits against the scroll range
  // as it existed when the animation began; if content above the target shifts
  // (the plan list growing after generation), the view strands at the target's
  // previous, higher offset instead of reaching the section.
  const duration = 420;
  const startTop = main.scrollTop;
  const startTime = (window.performance?.now?.() ?? Date.now());
  const animate = (now) => {
    const elapsed = (now ?? (window.performance?.now?.() ?? Date.now())) - startTime;
    const progress = Math.min(1, elapsed / duration);
    const eased = 1 - Math.pow(1 - progress, 3);
    const dest = targetTop();
    if (progress < 1 && Math.abs(dest - startTop) > 1) {
      main.scrollTo({ top: startTop + (dest - startTop) * eased, behavior: "auto" });
      window.requestAnimationFrame(animate);
      return;
    }
    main.scrollTo({ top: dest, behavior: "auto" });
    handleProgrammaticScroll();
  };
  main.addEventListener("scroll", handleProgrammaticScroll, { passive: true });
  window.requestAnimationFrame(animate);
}



function setActiveNavigation(target) {
  document.querySelectorAll(".sidebar .step[href^='#']").forEach((link) => {
    const selected = link.getAttribute("href") === target;
    link.classList.toggle("active", selected);
    if (selected) link.setAttribute("aria-current", link.dataset.section ? "step" : "page");
    else link.removeAttribute("aria-current");
  });
}



function toggleSidebar() {
  const open = !$("app-shell").classList.contains("sidebar-open");
  if (!open) { closeSidebar(true); return; }
  $("sidebar").inert = false;
  $("sidebar").removeAttribute("aria-hidden");
  $("app-shell").classList.toggle("sidebar-open", open);
  $("sidebar-toggle").setAttribute("aria-expanded", String(open));
  $("sidebar-toggle").setAttribute("aria-label", open ? t("sidebar.close") : t("sidebar.open"));
  window.setTimeout(() => $("sidebar").querySelector(".step.active")?.focus(), 210);
}



function closeSidebar(returnFocus = true) {
  const focusWasInside = $("sidebar")?.contains(document.activeElement);
  $("app-shell")?.classList.remove("sidebar-open");
  $("sidebar-toggle")?.setAttribute("aria-expanded", "false");
  $("sidebar-toggle")?.setAttribute("aria-label", t("sidebar.open"));
  syncSidebarAccessibility();
  if (returnFocus && focusWasInside) $("sidebar-toggle")?.focus();
}



function syncSidebarAccessibility() {
  const sidebar = $("sidebar"); const shell = $("app-shell");
  if (!sidebar || !shell) return;
  const hiddenOnMobile = window.innerWidth < 900 && !shell.classList.contains("sidebar-open");
  sidebar.inert = hiddenOnMobile;
  if (hiddenOnMobile) sidebar.setAttribute("aria-hidden", "true"); else sidebar.removeAttribute("aria-hidden");
}



function handleGlobalKeyDown(event) {
  if (event.key !== "Escape") return;
  closeAllCustomSelects();
  if ($("app-shell")?.classList.contains("sidebar-open")) closeSidebar(true);
  if ($("theme-menu")) $("theme-menu").open = false;
  if ($("language-menu")) $("language-menu").open = false;
}



function renderOfflineShell() {
  setRuntimeStatus(t("status.bridgeWaiting"), "warn");
  setText("sidebar-config-path", t("summary.waitingForBridge"));
  renderSummary($("config-summary"), [[t("summary.configPath"), t("summary.waitingForBridge")], [t("summary.configFile"), t("summary.unavailable")]]);
  renderSummary($("mkvmerge-summary"), [[t("summary.status"), t("summary.unavailable")], [t("summary.resolvedPath"), t("summary.waitingForBridge")]]);
}


