from argparse import Namespace
from pathlib import Path

import pytest

from plexmuxy.config import ConfigError, default_config
from plexmuxy.overrides import (
    JobOverrides,
    apply_job_overrides,
    overrides_from_namespace,
    overrides_from_payload,
)


def test_apply_job_overrides_updates_task_fields_without_mutating_original(tmp_path):
    config = default_config()
    updated = apply_job_overrides(
        config,
        JobOverrides(
            cleanup="delete",
            extra_dir="Archive",
            output_suffix="_Ready",
            output_dir=str(tmp_path / "out"),
            name_strategy="template",
            name_template="{stem}.plex",
            font_mode="subset",
            overwrite=True,
        ),
    )

    assert config.task.cleanup == "move"
    assert updated.task.cleanup == "delete"
    assert updated.task.cleanup_overridden is True
    assert updated.task.extra_dir == "Archive"
    assert updated.task.output_suffix == "_Ready"
    assert updated.task.output_dir == tmp_path / "out"
    assert updated.task.name_strategy == "template"
    assert updated.task.name_template == "{stem}.plex"
    assert updated.font.mode == "subset"
    assert updated.task.overwrite is True


def test_empty_string_overrides_do_not_pollute_optional_fields():
    config = default_config()
    config.task.extra_dir = "Extra"
    config.task.output_dir = Path("Existing")
    config.task.name_template = "existing"

    updated = apply_job_overrides(
        config,
        overrides_from_payload(
            {
                "extra_dir": "",
                "output_suffix": "",
                "output_dir": "",
                "name_template": "",
                "overwrite": False,
            }
        ),
    )

    assert updated.task.extra_dir == "Extra"
    assert updated.task.output_suffix == "_Plex"
    assert updated.task.output_dir == Path("Existing")
    assert updated.task.name_template == "existing"
    assert updated.task.overwrite is False


def test_missing_cleanup_override_preserves_cleanup_overridden_flag():
    config = default_config()
    config.task.cleanup = "move"
    config.task.cleanup_overridden = False

    updated = apply_job_overrides(config, JobOverrides(cleanup=None))

    assert updated.task.cleanup == "move"
    assert updated.task.cleanup_overridden is False


def test_cli_and_gui_payloads_use_same_override_model():
    namespace_overrides = overrides_from_namespace(
        Namespace(
            cleanup="none",
            extra_dir="Extra2",
            output_suffix="_Mux",
            output_dir="Ready",
            name_strategy="same-name",
            name_template=None,
            font_mode="referenced",
            overwrite=True,
        )
    )
    payload_overrides = overrides_from_payload(
        {
            "cleanup": "none",
            "extra_dir": "Extra2",
            "output_suffix": "_Mux",
            "output_dir": "Ready",
            "name_strategy": "same-name",
            "name_template": None,
            "font_mode": "referenced",
            "overwrite": True,
        }
    )

    assert namespace_overrides == payload_overrides


def test_invalid_font_mode_override_uses_config_validation():
    config = default_config()
    overrides = overrides_from_payload({"font_mode": "not-a-mode"})

    with pytest.raises(ConfigError, match=r"font\.mode"):
        apply_job_overrides(config, overrides)
