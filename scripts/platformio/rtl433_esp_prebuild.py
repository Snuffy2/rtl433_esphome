"""Prepare rtl_433_ESP library sources before PlatformIO compiles them."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

Import("env")  # type: ignore[name-defined]  # noqa: F821


class SourceNode(Protocol):
    """Protocol for the SCons source nodes passed through PlatformIO middleware."""

    def srcnode(self) -> SourceNode:
        """Return the original source node."""

    def get_path(self) -> str:
        """Return the source path."""


DUPLICATE_DECODER_UTIL_SUFFIX = (
    "rtl_433_ESP",
    "src",
    "rtl_433",
    "decoder_util copy.c",
)


def is_duplicate_decoder_util_source(source_path: str | Path) -> bool:
    """Return whether a source path is the duplicate rtl_433 decoder utility file.

    Args:
        source_path: Source path collected by PlatformIO.

    Returns:
        True when the source path points to the duplicate decoder utility file.
    """

    return Path(source_path).parts[-len(DUPLICATE_DECODER_UTIL_SUFFIX) :] == (
        DUPLICATE_DECODER_UTIL_SUFFIX
    )


def skip_duplicate_decoder_util_source(node: SourceNode) -> SourceNode | None:
    """Skip the duplicate decoder utility source shipped in rtl_433_ESP v0.5.0.

    Args:
        node: PlatformIO source node.

    Returns:
        The original node unless it is the duplicate decoder utility source.
    """

    if is_duplicate_decoder_util_source(node.srcnode().get_path()):
        return None
    return node


env.AddBuildMiddleware(skip_duplicate_decoder_util_source)  # type: ignore[name-defined]  # noqa: F821
