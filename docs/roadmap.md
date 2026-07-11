# Deferred follow-up work

The 0.2 scope intentionally preserves source tracks and full/referenced fonts. Proposed follow-up issues:

- ASS/SSA font alias analysis and richer missing-font reporting.
- True glyph subsetting with fontTools, including CJK, shaping, OpenType features, TTC collections, and deterministic full-font fallback.
- Source audio preview and explicit commentary/language/title filters; unknown tracks must be kept.
- Multi-directory queue, persisted job history, and safe manual plan editing.
- Internationalized CLI/GUI resources and optional update checks.
- Optional Plex library scan integration isolated from the mux transaction.
