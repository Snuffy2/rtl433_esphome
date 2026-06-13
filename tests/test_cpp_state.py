"""Host tests for the pure C++ rtl433 gateway state layer."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import subprocess


def test_rtl433_state_cpp(
    compile_and_run_cpp: Callable[[Path], subprocess.CompletedProcess[str]],
) -> None:
    """Compile and run the C++ state test binary."""

    source = Path(__file__).resolve().parent / "cpp/test_rtl433_state.cpp"
    result = compile_and_run_cpp(source)
    assert result.returncode == 0, result.stderr + result.stdout
