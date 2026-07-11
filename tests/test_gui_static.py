from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_gui_dynamic_rendering_does_not_use_inner_html():
    javascript = (ROOT / "plexmuxy_gui" / "static" / "app.js").read_text(encoding="utf-8")
    assert "innerHTML" not in javascript
    assert "textContent" in javascript


def test_gui_exposes_live_status_and_cancel_control():
    html = (ROOT / "plexmuxy_gui" / "static" / "index.html").read_text(encoding="utf-8")
    assert 'aria-live="polite"' in html
    assert 'id="cancel-btn"' in html
    assert 'role="alert"' in html
