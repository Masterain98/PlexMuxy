import re
from importlib.resources import files

import plexmuxy


def test_package_version_comes_from_bundled_version_file():
    version = files("plexmuxy").joinpath("VERSION").read_text(encoding="utf-8").strip()

    assert re.fullmatch(r"\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?", version)
    assert plexmuxy.__version__ == version
