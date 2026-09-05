"""Pytest helpers for compiling small C++ host test binaries."""

from __future__ import annotations

from collections.abc import Callable
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import ModuleType

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / ".github" / "scripts" / "upload_release_asset.py"
)


@pytest.fixture(scope="session")
def uploader() -> ModuleType:
    """Load the release uploader module once for the test session.

    Returns:
        Imported release uploader module.

    Raises:
        RuntimeError: If the helper cannot be imported from its assigned path.
    """
    spec = importlib.util.spec_from_file_location("upload_release_asset", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


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
    if shutil.which(compiler) is None:
        pytest.skip(f"C++ compiler '{compiler}' is not available on PATH.", allow_module_level=True)

    state_source = repo_root / "components/rtl433_native/rtl433_state.cpp"
    if not state_source.exists():
        pytest.fail(
            f"Missing expected C++ source file: {state_source}. "
            "Create components/rtl433_native/rtl433_state.cpp before running C++ tests."
        )

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
            str(state_source),
            "-o",
            str(binary),
        ]
        subprocess.run(command, check=True, text=True, capture_output=True)
        return subprocess.run([str(binary)], check=False, text=True, capture_output=True)

    return _compile_and_run
