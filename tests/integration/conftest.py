import shutil
import subprocess

import pytest


@pytest.fixture(scope="session")
def media_tools():
    ffmpeg = shutil.which("ffmpeg")
    mkvmerge = shutil.which("mkvmerge")
    if not ffmpeg or not mkvmerge:
        pytest.skip("integration tests require ffmpeg and mkvmerge")
    return ffmpeg, mkvmerge


def run_checked(command):
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode:
        pytest.fail(completed.stderr)
