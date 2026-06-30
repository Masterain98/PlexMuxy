from pathlib import Path

import pytest

from plexmuxy.config import default_config
from plexmuxy.subtitle import build_track_name, detect_subtitle_author, detect_subtitle_info, is_font_file


@pytest.fixture()
def subtitle_config():
    return default_config().subtitle


@pytest.mark.parametrize(
    ("name", "language", "mkv_language", "ietf_language"),
    [
        ("Example.chs.ass", "chs", "chi", "zh-Hans"),
        ("Example.cht.ass", "cht", "chi", "zh-Hant"),
        ("Example.jpn.ass", "jpn", "jpn", "ja"),
        ("Example.rus.ass", "rus", "rus", "ru"),
        ("Example.jpsc.ass", "jp_sc", "chi", "zh-Hans"),
    ],
)
def test_detect_subtitle_languages(subtitle_config, name, language, mkv_language, ietf_language):
    info = detect_subtitle_info(Path(name), subtitle_config)

    assert info.language == language
    assert info.mkv_language == mkv_language
    assert info.ietf_language == ietf_language


def test_detect_subtitle_author(subtitle_config):
    info = detect_subtitle_info(Path("[Kamigami] Example.chs.ass"), subtitle_config)

    assert info.sub_author == "Kamigami"
    assert detect_subtitle_author("[Kamigami] Example.chs.ass") == "Kamigami"


def test_unknown_subtitle_language_is_empty(subtitle_config):
    info = detect_subtitle_info(Path("Example.unknown.ass"), subtitle_config)

    assert info.language == ""
    assert info.mkv_language == ""
    assert info.ietf_language == ""


def test_jpsc_is_default_when_default_language_is_chs(subtitle_config):
    info = detect_subtitle_info(Path("Example.jpsc.ass"), subtitle_config)

    assert info.default_language is True


def test_detect_subtitle_info_prefers_most_specific_keyword(subtitle_config):
    subtitle_config.profiles = list(reversed(subtitle_config.profiles))
    info = detect_subtitle_info(Path("Example.jpsc.ass"), subtitle_config)

    assert info.language == "jp_sc"


def test_build_track_name_respects_author_setting(subtitle_config):
    info = detect_subtitle_info(Path("[Kamigami] Example.chs.ass"), subtitle_config)

    assert build_track_name(info, subtitle_config) == "chs Kamigami"
    subtitle_config.show_author_in_track_name = False
    assert build_track_name(info, subtitle_config) == "chs"


def test_build_track_name_without_author(subtitle_config):
    info = detect_subtitle_info(Path("Example.chs.ass"), subtitle_config)

    assert build_track_name(info, subtitle_config) == "chs"


def test_is_font_file_is_case_insensitive_and_allows_custom_extensions():
    assert is_font_file(Path("MyFont.TTF"), [".ttf", ".otf"])
    assert is_font_file(Path("AnotherFont.oTf"), ["otf"])
    assert not is_font_file(Path("NotAFont.ass"), [".ttf", ".otf"])
