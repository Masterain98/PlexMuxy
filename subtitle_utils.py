from config import get_config
import re

config = get_config()
# zh-CN
CHS_LIST = config["Subtitle"]["Keyword"]["CHS"]
# zh-TW or zh-HK
CHT_LIST = config["Subtitle"]["Keyword"]["CHT"]
# Jpn and zh-CN
JP_SC_LIST = config["Subtitle"]["Keyword"]["JP_SC"]
# Jpn and zh-TW/zh-HK
JP_TC_LIST = config["Subtitle"]["Keyword"]["JP_TC"]
# Jpn
JP_LIST = config["Subtitle"]["Keyword"]["JP"]
# Rus
RU_LIST = config["Subtitle"]["Keyword"]["RU"]
ALLOWED_FONT_EXTENSIONS = config["Font"]["AllowedExtensions"]


def subtitle_info_checker(subtitle_file_name: str) -> dict:
    """
    Check the subtitle file name and analyze language and group information
    :param subtitle_file_name: subtitle file name (path)
    :return: a dictionary of language and group information, empty string if not found
    """

    user_default_language = config["Subtitle"]["DefaultLanguage"]
    is_default_language = False

    if any(indicator in subtitle_file_name.lower() for indicator in JP_SC_LIST):
        language = "jp_sc"
        mkv_language = "chi"
        ietf_language = "zh-Hans"
    elif any(indicator in subtitle_file_name.lower() for indicator in JP_TC_LIST):
        language = "jp_tc"
        mkv_language = "chi"
        ietf_language = "zh-Hant"
    elif any(indicator in subtitle_file_name.lower() for indicator in CHS_LIST):
        language = "chs"
        mkv_language = "chi"
        ietf_language = "zh-Hans"
    elif any(indicator in subtitle_file_name.lower() for indicator in CHT_LIST):
        language = "cht"
        mkv_language = "chi"
        ietf_language = "zh-Hant"
    elif any(indicator in subtitle_file_name.lower() for indicator in JP_LIST):
        language = "jpn"
        mkv_language = "jpn"
        ietf_language = "ja"
    elif any(indicator in subtitle_file_name.lower() for indicator in RU_LIST):
        language = "rus"
        mkv_language = "rus"
        ietf_language = "ru"
    else:
        language = ""
        mkv_language = ""
        ietf_language = ""

    if language == user_default_language:
        is_default_language = True

    sub_author = re.search(r'(^\[)(\w|\d|-|_|&|\.|!)+(]+?)', subtitle_file_name)
    if sub_author is not None:
        sub_author = sub_author.group(0)
    else:
        sub_author = ""

    return {
        "language": language,
        "sub_author": sub_author.replace("[", "").replace("]", ""),
        "default_language": is_default_language,
        "mkv_language": mkv_language,
        "ietf_language": ietf_language
    }


def is_font_file(f: str) -> bool:
    """
    Check the file extension if is a font
    :param f: file name (path)
    :return: true if is a font file, false if not
    """
    if any(f.lower().endswith(ext) for ext in ALLOWED_FONT_EXTENSIONS):
        return True
    else:
        return False
