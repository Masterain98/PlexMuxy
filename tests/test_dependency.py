import importlib
import importlib.util
from importlib import metadata
from pathlib import Path

import pytest


def test_declared_pymkv2_dependency_uses_runtime_import_name():
    try:
        metadata.version("pymkv2")
    except metadata.PackageNotFoundError:
        pytest.skip("pymkv2 is not installed in this environment")

    assert importlib.util.find_spec("pymkv") is not None
    pymkv = importlib.import_module("pymkv")

    assert hasattr(pymkv, "MKVFile")
    assert hasattr(pymkv, "MKVTrack")


def test_dependency_files_match_runtime_import_name():
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    requirements = Path("requirements.txt").read_text(encoding="utf-8")

    assert "pymkv2>=2.3.2" in pyproject
    assert "pymkv2>=2.3.2" in requirements
    assert '"pymkv>=' not in pyproject
    assert "\npymkv>=" not in f"\n{requirements}"
    assert "setuptools<82" not in pyproject
    assert "setuptools<82" not in requirements
