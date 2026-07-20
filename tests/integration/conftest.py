import shutil
import subprocess

import pytest


@pytest.fixture(scope="session")
def ffmpeg_tool():
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("integration tests require ffmpeg")
    return ffmpeg


@pytest.fixture(scope="session")
def media_tools(ffmpeg_tool):
    ffmpeg = ffmpeg_tool
    mkvmerge = shutil.which("mkvmerge")
    if not mkvmerge:
        pytest.skip("integration tests require ffmpeg and mkvmerge")
    return ffmpeg, mkvmerge


def run_checked(command):
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode:
        pytest.fail(completed.stderr)
