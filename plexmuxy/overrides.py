from __future__ import annotations

import copy
from argparse import Namespace
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from .models import AppConfig, CleanupMode, NameStrategy


@dataclass
class JobOverrides:
    cleanup: str | None = None
    extra_dir: str | None = None
    output_suffix: str | None = None
    output_dir: str | None = None
    name_strategy: str | None = None
    name_template: str | None = None
    overwrite: bool = False


def apply_job_overrides(config: AppConfig, overrides: JobOverrides) -> AppConfig:
    updated = copy.deepcopy(config)
    if overrides.cleanup is not None:
        updated.task.cleanup = cast(CleanupMode, overrides.cleanup)
        updated.task.cleanup_overridden = True
    if overrides.extra_dir:
        updated.task.extra_dir = overrides.extra_dir
    if overrides.output_suffix is not None:
        updated.task.output_suffix = overrides.output_suffix or "_Plex"
    if overrides.output_dir:
        updated.task.output_dir = Path(overrides.output_dir).expanduser()
    if overrides.name_strategy:
        updated.task.name_strategy = cast(NameStrategy, overrides.name_strategy)
    if overrides.name_template:
        updated.task.name_template = overrides.name_template
    if overrides.overwrite:
        updated.task.overwrite = True
    # Reuse the same validation path as persisted configuration so malformed
    # CLI/GUI overrides never reach the planner.
    from .config import config_to_dict, parse_config

    validated = parse_config(config_to_dict(updated))
    validated.source_path = config.source_path
    return validated


def overrides_from_namespace(args: Namespace) -> JobOverrides:
    return JobOverrides(
        cleanup=getattr(args, "cleanup", None),
        extra_dir=getattr(args, "extra_dir", None),
        output_suffix=getattr(args, "output_suffix", None),
        output_dir=getattr(args, "output_dir", None),
        name_strategy=getattr(args, "name_strategy", None),
        name_template=getattr(args, "name_template", None),
        overwrite=bool(getattr(args, "overwrite", False)),
    )


def overrides_from_payload(payload: dict[str, Any]) -> JobOverrides:
    return JobOverrides(
        cleanup=optional_str(payload.get("cleanup")),
        extra_dir=optional_str(payload.get("extra_dir")),
        output_suffix=optional_str(payload.get("output_suffix"), keep_empty=True),
        output_dir=optional_str(payload.get("output_dir")),
        name_strategy=optional_str(payload.get("name_strategy")),
        name_template=optional_str(payload.get("name_template")),
        overwrite=bool(payload.get("overwrite", False)),
    )


def optional_str(value: Any, keep_empty: bool = False) -> str | None:
    if value is None:
        return None
    text = str(value)
    if text == "" and not keep_empty:
        return None
    return text
