"""Create a temporary firmware profile that builds the checked-out component."""

from __future__ import annotations

import argparse
from pathlib import Path
import re

GIT_COMPONENT_SOURCE = re.compile(
    r"^  - source:\n"
    r"      type: git\n"
    r"      url: \$\{rtl433_esphome_url\}\n"
    r"      ref: \$\{rtl433_esphome_ref\}",
    re.MULTILINE,
)


def parse_args() -> argparse.Namespace:
    """Parse temporary firmware-profile arguments.

    Returns:
        Parsed command-line arguments.
    """

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--components", type=Path, required=True)
    return parser.parse_args()


def prepare_config(source: Path, destination: Path, components: Path) -> None:
    """Replace exactly the known remote component source with a local source.

    Args:
        source: Repository firmware profile.
        destination: Temporary profile location.
        components: Checked-out component directory.

    Raises:
        ValueError: If the profile does not contain exactly one expected source.
    """

    component_path = components.resolve()
    if not component_path.is_dir():
        raise ValueError(f"Component directory does not exist: {component_path}")
    profile = source.read_text(encoding="utf-8")
    replacement = "  - source:\n      type: local\n      path: " + str(component_path)
    updated, replacements = GIT_COMPONENT_SOURCE.subn(replacement, profile)
    if replacements != 1:
        raise ValueError("Firmware profile must contain exactly one known git component source")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(updated, encoding="utf-8")


def main() -> None:
    """Write the requested temporary local-component firmware profile."""

    args = parse_args()
    try:
        prepare_config(args.source, args.destination, args.components)
    except (OSError, ValueError) as err:
        raise SystemExit(str(err)) from err


if __name__ == "__main__":
    main()
