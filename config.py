import warnings

warnings.warn("Top-level config.py is deprecated; import plexmuxy.config.", DeprecationWarning, stacklevel=2)

from plexmuxy.config import (
    ConfigError,
    default_config_dict,
    get_config,
    legacy_config_path,
    load_config,
    platform_config_path,
    resolve_config_path,
    save_config,
    write_default_config,
)

__all__ = [
    "ConfigError",
    "default_config_dict",
    "get_config",
    "legacy_config_path",
    "load_config",
    "platform_config_path",
    "resolve_config_path",
    "save_config",
    "write_default_config",
]
