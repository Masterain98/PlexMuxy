import json
import re
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_gui_dynamic_rendering_does_not_use_inner_html():
    javascript = (ROOT / "plexmuxy_gui" / "static" / "app.js").read_text(encoding="utf-8")
    i18n_javascript = (ROOT / "plexmuxy_gui" / "static" / "i18n.js").read_text(encoding="utf-8")
    assert "innerHTML" not in javascript
    assert "innerHTML" not in i18n_javascript
    assert "textContent" in javascript


def test_gui_exposes_live_status_and_cancel_control():
    html = (ROOT / "plexmuxy_gui" / "static" / "index.html").read_text(encoding="utf-8")
    assert 'aria-live="polite"' in html
    assert 'id="cancel-btn"' in html
    assert 'role="alert"' in html


def test_gui_provides_custom_frameless_window_controls():
    html = (ROOT / "plexmuxy_gui" / "static" / "index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "plexmuxy_gui" / "static" / "app.js").read_text(encoding="utf-8")

    assert 'class="window-drag-region pywebview-drag-region"' in html
    assert 'id="window-minimize-btn"' in html
    assert 'id="window-maximize-btn"' in html
    assert 'id="window-close-btn"' in html
    assert 'callApi("minimize_window")' in javascript
    assert 'callApi("toggle_maximize_window")' in javascript
    assert 'callApi("close_window")' in javascript


def test_gui_ships_and_references_approved_brand_assets():
    static_dir = ROOT / "plexmuxy_gui" / "static"
    asset_dir = static_dir / "assets"
    html = (static_dir / "index.html").read_text(encoding="utf-8")
    package_config = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    source_assets = {
        "plexmuxy-app-icon.svg": ROOT / "logo" / "svg" / "plexmuxy-app-icon.svg",
        "plexmuxy-app-icon-32.png": ROOT / "logo" / "png" / "plexmuxy-app-icon-32.png",
        "plexmuxy-app-icon-64.png": ROOT / "logo" / "png" / "plexmuxy-app-icon-64.png",
        "plexmuxy-app.ico": ROOT / "logo" / "plexmuxy-app.ico",
    }
    for name, source in source_assets.items():
        packaged = asset_dir / name
        assert packaged.read_bytes() == source.read_bytes()

    assert 'href="./assets/plexmuxy-app-icon.svg"' in html
    assert 'href="./assets/plexmuxy-app-icon-32.png"' in html
    assert 'href="./assets/plexmuxy-app-icon-64.png"' in html
    assert 'src="./assets/plexmuxy-app-icon-64.png"' in html
    assert "data:image/svg+xml" not in html
    assert '"static/assets/*.svg"' in package_config
    assert '"static/assets/*.png"' in package_config
    assert '"static/assets/*.ico"' in package_config


def test_windows_binaries_and_readmes_use_approved_brand_assets():
    gui_spec = (ROOT / "plexmuxy-gui.spec").read_text(encoding="utf-8")
    cli_spec = (ROOT / "plexmuxy-cli.spec").read_text(encoding="utf-8")
    readmes = [
        (ROOT / "README.md").read_text(encoding="utf-8"),
        (ROOT / "README.CN.md").read_text(encoding="utf-8"),
    ]

    assert 'icon="logo/plexmuxy-app.ico"' in gui_spec
    assert 'icon="logo/plexmuxy-app.ico"' in cli_spec
    assert 'pathex=["."]' in gui_spec
    assert 'pathex=["."]' in cli_spec
    for readme in readmes:
        assert "./logo/svg/plexmuxy-lockup-dark.svg" in readme
        assert "./logo/svg/plexmuxy-lockup-light.svg" in readme


def test_gui_implements_product_themes_and_desktop_navigation():
    html = (ROOT / "plexmuxy_gui" / "static" / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "plexmuxy_gui" / "static" / "app.css").read_text(encoding="utf-8")
    javascript = (ROOT / "plexmuxy_gui" / "static" / "app.js").read_text(encoding="utf-8")

    assert 'data-theme-mode="system"' in html
    assert 'data-theme-mode="light"' in html
    assert 'data-theme-mode="dark"' in html
    assert 'localStorage.getItem("plexmuxy-theme")' in html
    assert 'class="skip-link"' in html
    assert 'id="sidebar-toggle"' in html
    assert "grid-template-columns: 260px minmax(0, 1fr)" in css
    assert "@media (max-width: 1199px)" in css
    assert "IntersectionObserver" in javascript


def test_gui_includes_localized_about_page_and_safe_project_links():
    static_dir = ROOT / "plexmuxy_gui" / "static"
    html = (static_dir / "index.html").read_text(encoding="utf-8")
    javascript = (static_dir / "app.js").read_text(encoding="utf-8")
    english = json.loads((static_dir / "locales" / "en.json").read_text(encoding="utf-8"))
    chinese = json.loads((static_dir / "locales" / "zh-CN.json").read_text(encoding="utf-8"))

    assert 'href="#/about"' in html
    assert 'id="about-view"' in html
    assert html.index('</nav>') < html.index('href="#/about"')
    assert html.index('class="sidebar-footer"') < html.index('href="#/about"')
    assert 'src="assets/plexmuxy-app-icon.svg"' in html
    assert 'class="nav-project-icon"' in html
    assert 'id="about-version"' in html
    assert 'data-project-link="repository"' in html
    assert 'data-project-link="contributors"' not in html
    assert 'data-project-link="pywebview"' in html
    assert 'data-project-link="ffmpeg"' in html
    assert 'data-project-link="mkvtoolnix"' in html
    assert "Creator and maintainer" not in html
    assert "View contributors" not in html
    assert 'callApi("open_project_link", button.dataset.projectLink)' in javascript
    assert 'if (parts[0] === "about")' in javascript
    assert ".sidebar .step[href^='#']" in javascript
    assert "about.credits.creatorBody" not in english
    assert "about.credits.creatorBody" not in chinese
    assert english["about.credits.pywebview"]
    assert chinese["about.credits.pywebview"]
    assert "local-first" not in english["about.description"].casefold()
    assert "本地优先" not in chinese["about.description"]
    assert "scrollToSection" in javascript


def test_gui_uses_inline_feedback_and_accessible_confirmation():
    html = (ROOT / "plexmuxy_gui" / "static" / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "plexmuxy_gui" / "static" / "app.css").read_text(encoding="utf-8")
    javascript = (ROOT / "plexmuxy_gui" / "static" / "app.js").read_text(encoding="utf-8")

    assert 'class="activity-banner hidden"' in html
    assert 'id="confirm-dialog"' in html
    assert 'id="alert-message"' in html
    assert ".activity-progress" in css
    assert ".spinner" not in css
    assert "dialog.showModal()" in javascript
    assert "window.confirm" not in javascript


def test_gui_locks_clicked_navigation_during_programmatic_scroll():
    javascript = (ROOT / "plexmuxy_gui" / "static" / "app.js").read_text(encoding="utf-8")

    assert "navigationTarget" in javascript
    assert "navigationScrollCleanup" in javascript
    assert "if (state.navigationTarget) { setActiveNavigation(state.navigationTarget); return; }" in javascript
    assert 'main.addEventListener("scroll", handleProgrammaticScroll' in javascript


def test_gui_provides_extensible_i18n_with_simplified_chinese():
    html = (ROOT / "plexmuxy_gui" / "static" / "index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "plexmuxy_gui" / "static" / "app.js").read_text(encoding="utf-8")
    i18n_javascript = (ROOT / "plexmuxy_gui" / "static" / "i18n.js").read_text(encoding="utf-8")
    package_config = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    crowdin_config = (ROOT / "crowdin.yml").read_text(encoding="utf-8")

    assert html.index('<script src="./i18n.js"></script>') < html.index('<script src="./app.js"></script>')
    assert 'data-locale-mode="system"' in html
    assert 'data-locale-mode="zh-CN"' in html
    assert 'data-i18n="source.title"' in html
    assert 'data-i18n-aria-label="language.choose"' in html
    assert 'data-i18n-placeholder="source.placeholder"' in html
    assert 'const STORAGE_KEY = "plexmuxy-locale"' in i18n_javascript
    assert 'file: "./locales/en.json"' in i18n_javascript
    assert 'file: "./locales/zh-CN.json"' in i18n_javascript
    assert 'file: "./locales/zh-TW.json"' in i18n_javascript
    assert 'file: "./locales/ru.json"' in i18n_javascript
    assert "await fetch(" in i18n_javascript
    assert "async function loadCatalog" in i18n_javascript
    assert 'window.PlexMuxyI18n' in i18n_javascript
    assert 'window.addEventListener("plexmuxy:localechange"' in javascript
    assert '"static/locales/*.json"' in package_config
    assert 'source: "/plexmuxy_gui/static/locales/en.json"' in crowdin_config
    assert 'translation: "/plexmuxy_gui/static/locales/%locale%.json"' in crowdin_config


def test_gui_locale_catalogs_have_matching_keys_and_placeholders():
    locale_dir = ROOT / "plexmuxy_gui" / "static" / "locales"
    english = json.loads((locale_dir / "en.json").read_text(encoding="utf-8"))
    placeholder_pattern = re.compile(r"\{([\w-]+)\}")

    assert english
    assert all(isinstance(value, str) for value in english.values())

    for catalog_path in sorted(locale_dir.glob("*.json")):
        if catalog_path.name == "en.json":
            continue
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        assert english.keys() == catalog.keys(), catalog_path.name
        assert all(isinstance(value, str) for value in catalog.values())
        for key, source_text in english.items():
            assert set(placeholder_pattern.findall(source_text)) == set(placeholder_pattern.findall(catalog[key])), f"{catalog_path.name}:{key}"


def test_gui_source_catalog_covers_static_and_dynamic_translation_keys():
    static_dir = ROOT / "plexmuxy_gui" / "static"
    html = (static_dir / "index.html").read_text(encoding="utf-8")
    javascript = (static_dir / "app.js").read_text(encoding="utf-8")
    english = json.loads((static_dir / "locales" / "en.json").read_text(encoding="utf-8"))

    used_keys = set(re.findall(r'data-i18n(?:-[\w-]+)?="([\w.-]+)"', html))
    used_keys.update(re.findall(r'\bt\("([\w.-]+)"', javascript))

    assert used_keys
    assert used_keys <= english.keys()


def test_gui_separates_workspace_and_persistent_environment_routes():
    static_dir = ROOT / "plexmuxy_gui" / "static"
    html = (static_dir / "index.html").read_text(encoding="utf-8")
    javascript = (static_dir / "app.js").read_text(encoding="utf-8")

    assert 'id="workspace-view"' in html
    assert 'id="environment-view"' in html
    assert 'href="#/environment"' in html
    assert 'href="#/workspace/directory-section"' in html
    assert "function parseRoute" in javascript
    assert "function handleRoute" in javascript
    assert 'state.currentView = route.view' in javascript


def test_gui_replaces_native_selects_with_accessible_listboxes():
    static_dir = ROOT / "plexmuxy_gui" / "static"
    html = (static_dir / "index.html").read_text(encoding="utf-8")
    javascript = (static_dir / "app.js").read_text(encoding="utf-8")
    css = (static_dir / "app.css").read_text(encoding="utf-8")

    assert "<select" not in html
    assert html.count('role="combobox"') == 3
    assert html.count('role="listbox"') == 3
    assert 'aria-haspopup="listbox"' in html
    for behavior in (
        "handleSelectTriggerKey",
        "handleSelectOptionKey",
        "findTypeaheadMatch",
        "handleOutsideSelectPointer",
        "opens-up",
    ):
        assert behavior in javascript
    assert '.select-listbox [role="option"][aria-selected="true"]' in css


def test_gui_uses_toasts_for_transient_results_and_custom_close_confirmation():
    static_dir = ROOT / "plexmuxy_gui" / "static"
    html = (static_dir / "index.html").read_text(encoding="utf-8")
    javascript = (static_dir / "app.js").read_text(encoding="utf-8")

    assert 'id="toast-region"' in html
    assert 'id="close-dialog"' in html
    assert 'callApi("open_diagnostics_location")' in javascript
    assert "function showToast" in javascript
    assert "window.PlexMuxyRequestClose = closeWindow" in javascript
    assert 'setRuntimeStatus(t("status.diagnostics"' not in javascript
    assert 'setRuntimeStatus(t("status.settingsSaved"' not in javascript


def test_gui_exposes_persistent_dependency_paths_notifications_and_font_subsetting():
    static_dir = ROOT / "plexmuxy_gui" / "static"
    html = (static_dir / "index.html").read_text(encoding="utf-8")
    javascript = (static_dir / "app.js").read_text(encoding="utf-8")

    for identifier in (
        "mkvmerge-path",
        "ffmpeg-path",
        "unrar-path",
        "notifications-enabled",
        "test-notification-btn",
        "font-subset",
    ):
        assert f'id="{identifier}"' in html
    assert 'callApi("choose_dependency", dependency)' in javascript
    assert 'callApi("save_environment_settings"' in javascript
    assert 'callApi("test_notification"' in javascript
    assert 'font_mode: $("font-subset").checked ? "subset" : state.lastNonSubsetFontMode' in javascript
    assert "font_subset_intent?.summary" in javascript
    assert "completed_families" in javascript
    for phase in ("running_mux", "verifying_outputs", "subsetting_fonts", "validating_subsets"):
        assert f'"progress.phase.{phase}"' in (static_dir / "locales" / "en.json").read_text(encoding="utf-8")


def test_environment_dependencies_use_verified_draft_workflow():
    static_dir = ROOT / "plexmuxy_gui" / "static"
    html = (static_dir / "index.html").read_text(encoding="utf-8")
    javascript = (static_dir / "app.js").read_text(encoding="utf-8")
    chinese = (static_dir / "locales" / "zh-CN.json").read_text(encoding="utf-8")

    assert "恢复自动检测" not in html + javascript + chinese
    assert html.count('class="dependency-state" role="status"') == 3
    assert all(icon in html + javascript for icon in ("#icon-check", "#icon-question", "#icon-x"))
    assert 'id="install-unrar-btn"' in html
    assert 'callApi("detect_dependency", dependency)' in javascript
    assert 'callApi("install_unrar_from_rarlab")' in javascript
    assert "dependencyDrafts" in javascript


def test_gui_disables_every_workflow_input_while_busy():
    javascript = (ROOT / "plexmuxy_gui" / "static" / "app.js").read_text(encoding="utf-8")

    assert '"input-dir", "cleanup", "extra-dir", "output-dir", "output-suffix"' in javascript
    assert '"name-strategy", "name-template", "font-subset", "overwrite"' in javascript
    assert "control.disabled = busy" in javascript
    assert 'control.setAttribute("aria-disabled", String(busy))' in javascript


def test_gui_exposes_independent_plex_refresh_retry():
    javascript = (ROOT / "plexmuxy_gui" / "static" / "app.js").read_text(encoding="utf-8")

    assert 'callApi("retry_plex_refresh", job.id)' in javascript
    assert 'state.config?.plex?.enabled' in javascript


def test_gui_has_high_contrast_disabled_and_per_monitor_v2_support():
    css = (ROOT / "plexmuxy_gui" / "static" / "app.css").read_text(encoding="utf-8")
    manifest = (ROOT / "packaging" / "plexmuxy-gui.manifest").read_text(encoding="utf-8")
    spec = (ROOT / "plexmuxy-gui.spec").read_text(encoding="utf-8")

    assert "@media (forced-colors: active)" in css
    assert "input:disabled" in css
    assert "max-height: calc(100dvh - 32px)" in css
    assert "PerMonitorV2,PerMonitor" in manifest
    assert 'manifest="packaging/plexmuxy-gui.manifest"' in spec
