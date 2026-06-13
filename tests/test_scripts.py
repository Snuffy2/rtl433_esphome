"""Regression tests for repository shell scripts."""

from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import shlex
import subprocess
from typing import Callable, cast

import pytest


REPO_ROOT: Path = Path(__file__).resolve().parents[1]
PLATFORMIO_SCRIPT_ROOT: Path = REPO_ROOT / "scripts" / "platformio"


def copy_script(tmp_path: Path, name: str) -> Path:
    """Copy an executable repository script into a temporary repo root.

    Args:
        tmp_path: Temporary repository root.
        name: Script filename to copy.

    Returns:
        Path to the copied script.
    """
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir(exist_ok=True)
    destination = scripts_dir / name
    shutil.copy(REPO_ROOT / "scripts" / name, destination)
    destination.chmod(0o755)
    return destination


def install_python_stub(tmp_path: Path, generated_platformio_ini: Path | None = None) -> Path:
    """Install a fake venv Python executable that logs invocations.

    Args:
        tmp_path: Temporary repository root.
        generated_platformio_ini: Optional PlatformIO config to create when
            the fake ESPHome command generates build files.

    Returns:
        Path to the invocation log file.
    """
    python_path = tmp_path / ".venv" / "bin" / "python"
    python_path.parent.mkdir(parents=True)
    log_path = tmp_path / "python.log"
    script_lines = [
        "#!/usr/bin/env bash",
        f"printf '%s\\n' \"$*\" >> {shlex.quote(str(log_path))}",
    ]
    if generated_platformio_ini is not None:
        script_lines.extend(
            [
                ('if [[ "$*" == "-m esphome compile --only-generate garage-rtl433.yaml" ]]; then'),
                f"  mkdir -p {shlex.quote(str(generated_platformio_ini.parent))}",
                (
                    "  printf '%s\\n' "
                    "'platform=https://example.invalid/generated.zip' "
                    f"> {shlex.quote(str(generated_platformio_ini))}"
                ),
                "fi",
            ]
        )
    python_path.write_text("\n".join(script_lines) + "\n", encoding="utf-8")
    python_path.chmod(0o755)
    return log_path


def install_preflight_stub(tmp_path: Path) -> Path:
    """Install a fake preflight executable that logs invocations.

    Args:
        tmp_path: Temporary repository root.

    Returns:
        Path to the invocation log file.
    """
    preflight_log = tmp_path / "preflight.log"
    preflight = tmp_path / "scripts" / "esphome-preflight"
    preflight.write_text(
        f"#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> {preflight_log}\n",
        encoding="utf-8",
    )
    preflight.chmod(0o755)
    return preflight_log


def run_script(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run a copied shell script from its temporary repo root.

    Args:
        script: Script path under the temporary repo root.
        *args: Arguments to pass to the script.

    Returns:
        Completed process for assertions.
    """
    return subprocess.run(
        [str(script), *args],
        cwd=script.parents[1],
        check=False,
        text=True,
        capture_output=True,
    )


class FakePlatformIOEnv:
    """Test double for PlatformIO's SCons environment."""

    def __init__(self) -> None:
        """Initialize recorded build middleware callbacks."""

        self.build_middlewares: list[Callable[[object], object | None]] = []

    def AddBuildMiddleware(self, callback: Callable[[object], object | None]) -> None:  # noqa: N802
        """Record a PlatformIO build middleware callback."""

        self.build_middlewares.append(callback)


@dataclass(frozen=True)
class FakeSourceNode:
    """Test double for a SCons source node."""

    path: str

    def srcnode(self) -> FakeSourceNode:
        """Return the original source node."""

        return self

    def get_path(self) -> str:
        """Return the source path."""

        return self.path


def load_platformio_prebuild_script(
    script_name: str,
) -> tuple[dict[str, object], FakePlatformIOEnv]:
    """Load a PlatformIO prebuild script without requiring SCons.

    Args:
        script_name: Filename under scripts/platformio.

    Returns:
        Executed script globals and fake PlatformIO environment.
    """

    fake_env = FakePlatformIOEnv()
    namespace: dict[str, object] = {
        "Import": lambda *_args: None,
        "env": fake_env,
    }
    script = PLATFORMIO_SCRIPT_ROOT / script_name
    exec(script.read_text(encoding="utf-8"), namespace)
    return namespace, fake_env


def test_rtl433_esp_prebuild_skips_duplicate_decoder_source() -> None:
    """rtl_433_ESP v0.5.0 should not compile its duplicate decoder utility file."""
    namespace, fake_env = load_platformio_prebuild_script("rtl433_esp_prebuild.py")
    is_duplicate_decoder_util_source = cast(
        Callable[[str], bool], namespace["is_duplicate_decoder_util_source"]
    )
    middleware = fake_env.build_middlewares[0]
    duplicate_node = FakeSourceNode(
        "/tmp/libdeps/garage-rtl433-native/rtl_433_ESP/src/rtl_433/decoder_util copy.c"
    )
    canonical_node = FakeSourceNode(
        "/tmp/libdeps/garage-rtl433-native/rtl_433_ESP/src/rtl_433/decoder_util.c"
    )

    assert is_duplicate_decoder_util_source(duplicate_node.path)
    assert middleware(duplicate_node) is None
    assert middleware(canonical_node) == canonical_node


def test_build_defaults_to_compile_without_preflight(tmp_path: Path) -> None:
    """The default build path should not run package-maintenance preflight."""
    script = copy_script(tmp_path, "build")
    python_log = install_python_stub(tmp_path)
    preflight_log = install_preflight_stub(tmp_path)

    result = run_script(script)

    assert result.returncode == 0, result.stderr
    assert python_log.read_text(encoding="utf-8").splitlines() == [
        "-m esphome config garage-rtl433.yaml",
        "-m esphome compile garage-rtl433.yaml",
    ]
    assert not preflight_log.exists()


@pytest.mark.parametrize(
    ("extra_args", "expected_preflight_args"),
    [
        (("--update-global",), "--update-global .esphome/build/generated-node/platformio.ini"),
        ((), ".esphome/build/generated-node/platformio.ini"),
    ],
)
def test_build_preflight_modes(
    tmp_path: Path, extra_args: tuple[str, ...], expected_preflight_args: str
) -> None:
    """Preflight builds should pass the freshly generated PlatformIO config."""
    script = copy_script(tmp_path, "build")
    stale_platformio_ini = tmp_path / ".esphome" / "build" / "old-node" / "platformio.ini"
    stale_platformio_ini.parent.mkdir(parents=True)
    stale_platformio_ini.write_text(
        "platform=https://example.invalid/stale.zip\n",
        encoding="utf-8",
    )
    os.utime(stale_platformio_ini, (1, 1))
    generated_platformio_ini = tmp_path / ".esphome" / "build" / "generated-node" / "platformio.ini"
    install_python_stub(tmp_path, generated_platformio_ini=generated_platformio_ini)
    preflight_log = install_preflight_stub(tmp_path)

    result = run_script(script, "--preflight", *extra_args)

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "python.log").read_text(encoding="utf-8").splitlines() == [
        "-m esphome config garage-rtl433.yaml",
        "-m esphome compile --only-generate garage-rtl433.yaml",
        "-m esphome compile garage-rtl433.yaml",
    ]
    assert preflight_log.read_text(encoding="utf-8").splitlines() == [expected_preflight_args]


def test_esphome_preflight_discovers_generated_platformio_ini(tmp_path: Path) -> None:
    """Preflight should discover the generated PlatformIO config dynamically."""
    script = copy_script(tmp_path, "esphome-preflight")
    python_log = install_python_stub(tmp_path)
    platformio_ini = tmp_path / ".esphome" / "build" / "renamed-node" / "platformio.ini"
    platformio_ini.parent.mkdir(parents=True)
    platformio_ini.write_text(
        "platform=https://example.invalid/platform-espressif32.zip\n",
        encoding="utf-8",
    )

    result = run_script(script)

    assert result.returncode == 0, result.stderr
    assert python_log.read_text(encoding="utf-8").splitlines() == [
        "-m platformio pkg install -g -f -p https://example.invalid/platform-espressif32.zip"
    ]


def test_package_firmware_copies_binaries_and_manifest(tmp_path: Path) -> None:
    """Packaging should preserve firmware outputs and create a web manifest."""
    script = copy_script(tmp_path, "package-firmware")
    firmware_dir = tmp_path / ".esphome" / "build" / "node" / ".pioenvs" / "node"
    firmware_dir.mkdir(parents=True)
    expected_files = {
        "bootloader.bin",
        "firmware.bin",
        "firmware.elf",
        "firmware.factory.bin",
        "firmware.ota.bin",
        "partitions.bin",
    }
    for filename in expected_files:
        (firmware_dir / filename).write_text(filename, encoding="utf-8")
    output_dir = tmp_path / "output" / "v1.2.3"

    result = run_script(script, "v1.2.3", str(output_dir))

    assert result.returncode == 0, result.stderr
    assert expected_files.issubset({path.name for path in output_dir.iterdir()})
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    factory_content = (firmware_dir / "firmware.factory.bin").read_bytes()
    ota_content = (firmware_dir / "firmware.ota.bin").read_bytes()
    assert manifest == {
        "name": "Garage RTL433",
        "version": "v1.2.3",
        "home_assistant_domain": "esphome",
        "new_install_prompt_erase": False,
        "builds": [
            {
                "chipFamily": "ESP32",
                "ota": {
                    "path": "firmware.ota.bin",
                    "md5": hashlib.md5(ota_content).hexdigest(),
                    "sha256": hashlib.sha256(ota_content).hexdigest(),
                },
                "parts": [
                    {
                        "path": "firmware.factory.bin",
                        "offset": 0,
                        "md5": hashlib.md5(factory_content).hexdigest(),
                        "sha256": hashlib.sha256(factory_content).hexdigest(),
                    }
                ],
            }
        ],
    }
