import os
import json

REQUIRED_CONFIG = ["TaskSettings", "Font", "SubtitleKeyword"]


def make_default_config():
    new_config = {
        "TaskSettings": {
            "DeleteFonts": False,
            "DeleteOriginalMKV": False,
            "DeleteOriginalMKA": False,
            "DeleteSubtitle": False,
            "OutputSuffixName": "_Plex"
        },
        "Font": {
            "AllowedExtensions": [".ttf", ".otf", ".ttc"]
        },
        "Subtitle": {
            "Keyword": {
                "CHS": [".chs", ".sc", "[chs]", "[sc]", ".gb", "[gb]"],
                "CHT": [".cht", ".tc", "[cht]", "[tc]", "big5", "[big5]"],
                "JP_SC": [".jpsc", "[jpsc]", "jp_sc", "[jp_sc]", "chs&jap", "简日"],
                "JP_TC": [".jptc", "[jptc]", "jp_tc", "[jp_tc]", "cht&jap", "繁日"],
                "JP": [".jp", ".jpn", ".jap", "[jp]", "[jpn]", "[jap]"],
                "RU": [".ru", ".rus", "[ru]", "[rus]"]
            },
            "DefaultLanguage": "chs"

        },
        "mkvmerge": {
            "path": "C:\\Program Files\\MKVToolNix\\mkvmerge.exe"
        }
    }
    with open(os.path.expandvars("%userprofile%/Documents/PlexMuxy.json"), "w", encoding='utf-8') as output:
        json.dump(new_config, output, indent=2, ensure_ascii=False)


def get_config() -> dict:
    if not os.path.exists(os.path.expandvars("%userprofile%/Documents/PlexMuxy.json")):
        print("Configuration file does not exist, creating default settings in [Document library folder]")
        make_default_config()
    with open(os.path.expandvars("%userprofile%/Documents/PlexMuxy.json"), "r", encoding='utf-8') as f:
        local_config = json.load(f)
    if any(item not in local_config.keys() for item in REQUIRED_CONFIG):
        raise ValueError("Config file does not meet requirements")
    return local_config
