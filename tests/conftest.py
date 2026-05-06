"""Pytest helpers for compiling small C++ host test binaries."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest


@pytest.fixture
def compile_and_run_cpp(tmp_path: Path) -> Callable[[Path], subprocess.CompletedProcess[str]]:
    """Return a helper that compiles and executes one C++ test file.

    Args:
        tmp_path: Pytest temporary directory for compiled binaries.

    Returns:
        A callable that compiles the supplied test source and returns the
        completed test process.
    """

    repo_root = Path(__file__).resolve().parents[1]
    compiler = os.environ.get("CXX", "c++")

    def _compile_and_run(source: Path) -> subprocess.CompletedProcess[str]:
        binary = tmp_path / source.stem
        command = [
            compiler,
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(repo_root),
            str(source),
            str(repo_root / "components/rtl433_native/rtl433_state.cpp"),
            "-o",
            str(binary),
        ]
        subprocess.run(command, check=True, text=True, capture_output=True)
        return subprocess.run([str(binary)], check=False, text=True, capture_output=True)

    return _compile_and_run
