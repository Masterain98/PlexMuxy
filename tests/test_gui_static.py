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
    simplified_chinese = json.loads((locale_dir / "zh-CN.json").read_text(encoding="utf-8"))

    assert english
    assert english.keys() == simplified_chinese.keys()
    assert all(isinstance(value, str) for value in english.values())
    assert all(isinstance(value, str) for value in simplified_chinese.values())

    placeholder_pattern = re.compile(r"\{([\w-]+)\}")
    for key, source_text in english.items():
        assert set(placeholder_pattern.findall(source_text)) == set(placeholder_pattern.findall(simplified_chinese[key])), key


def test_gui_source_catalog_covers_static_and_dynamic_translation_keys():
    static_dir = ROOT / "plexmuxy_gui" / "static"
    html = (static_dir / "index.html").read_text(encoding="utf-8")
    javascript = (static_dir / "app.js").read_text(encoding="utf-8")
    english = json.loads((static_dir / "locales" / "en.json").read_text(encoding="utf-8"))

    used_keys = set(re.findall(r'data-i18n(?:-[\w-]+)?="([\w.-]+)"', html))
    used_keys.update(re.findall(r'\bt\("([\w.-]+)"', javascript))

    assert used_keys
    assert used_keys <= english.keys()
