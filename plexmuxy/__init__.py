"""PlexMuxy media muxing toolkit."""

from importlib.resources import files

__all__ = ["__version__"]

__version__ = files("plexmuxy").joinpath("VERSION").read_text(encoding="utf-8").strip()
