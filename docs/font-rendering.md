# Font rendering validation

`tests/integration/test_libass_render.py` renders the same ASS frame twice through ffmpeg/libass: once with a complete locally generated font and once with the renamed subset. The raw RGBA frames must be identical and non-empty. The redistributable synthetic fixtures exercise CJK codepoints plus regular and bold-italic selection without depending on system fonts.

Unit coverage separately checks TTC multi-face extraction, unsafe color/bitmap fallback, missing glyph rejection, metadata preservation, corrupt-cache rebuilding, and deterministic output. New CFF/CFF2, variable, color/bitmap, complex-shaping, vertical-text, `\fn`, `\r`, or animated `\t()` support must add a legally redistributable fixture before its fallback is relaxed. Platform-specific antialiasing baselines should compare geometry independently from small pixel differences when exact raw frames are not portable.

HarfBuzz repacking remains an experiment, not a default dependency. It may be evaluated only after a real FontTools failure or render mismatch is captured, with the HarfBuzz version added to the cache compatibility key and full-font fallback retained. No current evidence justifies enabling a second subset engine.
