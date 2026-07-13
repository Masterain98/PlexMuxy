# Localization

PlexMuxy stores UI translations as UTF-8 JSON files in `plexmuxy_gui/static/locales/`.

- `en.json` is the source language and defines the canonical key set.
- Each translation uses one independent file named with its BCP 47 locale, such as `zh-CN.json`.
- Keys are stable identifiers. Translate values only.
- Placeholders such as `{count}`, `{path}`, and `{theme}` must remain unchanged in translated values.
- Empty translated values fall back to English at runtime.

## Crowdin

The root `crowdin.yml` uploads `en.json` as the source and downloads translations to `%locale%.json`. Project credentials are intentionally not stored in the repository; provide them through the Crowdin CLI or environment variables.

Typical commands after authenticating the Crowdin CLI:

```console
crowdin upload sources
crowdin download
```

The test suite verifies that committed catalogs have the same keys and preserve every placeholder.

## Adding a language

1. Add `plexmuxy_gui/static/locales/<locale>.json` using the same keys as `en.json`.
2. Register the locale and file in `LOCALES` inside `plexmuxy_gui/static/i18n.js`.
3. Add the language option to `plexmuxy_gui/static/index.html`.
4. Run `python -m pytest -q tests/test_gui_static.py`.
