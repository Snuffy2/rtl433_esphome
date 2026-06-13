"""Prepare rtl_433_ESP library sources before PlatformIO compiles them."""

from __future__ import annotations

from pathlib import Path

Import("env")  # type: ignore[name-defined]  # noqa: F821


def remove_duplicate_decoder_util(project_libdeps_dir: Path, pioenv: str) -> None:
    """Remove the duplicate decoder utility source shipped in rtl_433_ESP v0.5.0.

    Args:
        project_libdeps_dir: PlatformIO library dependencies directory.
        pioenv: Active PlatformIO environment name.
    """

    duplicate_source = (
        project_libdeps_dir / pioenv / "rtl_433_ESP" / "src" / "rtl_433" / "decoder_util copy.c"
    )
    duplicate_source.unlink(missing_ok=True)


remove_duplicate_decoder_util(
    Path(env["PROJECT_LIBDEPS_DIR"]),  # type: ignore[name-defined]  # noqa: F821
    env["PIOENV"],  # type: ignore[name-defined]  # noqa: F821
)
