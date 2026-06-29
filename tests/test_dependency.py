import importlib
import importlib.util
from pathlib import Path

import pytest


def test_declared_pymkv_dependency_uses_runtime_import_name():
    if importlib.util.find_spec("pymkv") is None:
        pytest.skip("pymkv is not installed in this environment")

    pymkv = importlib.import_module("pymkv")

    assert hasattr(pymkv, "MKVFile")
    assert hasattr(pymkv, "MKVTrack")


def test_dependency_files_match_runtime_import_name():
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    requirements = Path("requirements.txt").read_text(encoding="utf-8")

    assert "pymkv>=1.0.8" in pyproject
    assert "pymkv>=1.0.8" in requirements
    assert "pymkv2" not in pyproject
    assert "pymkv2" not in requirements
