"""Regression tests for repository shell scripts."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import hashlib


REPO_ROOT: Path = Path(__file__).resolve().parents[1]


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


def install_python_stub(tmp_path: Path) -> Path:
    """Install a fake venv Python executable that logs invocations.

    Args:
        tmp_path: Temporary repository root.

    Returns:
        Path to the invocation log file.
    """
    python_path = tmp_path / ".venv" / "bin" / "python"
    python_path.parent.mkdir(parents=True)
    log_path = tmp_path / "python.log"
    python_path.write_text(
        f"#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> {log_path}\n",
        encoding="utf-8",
    )
    python_path.chmod(0o755)
    return log_path


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


def test_build_defaults_to_compile_without_preflight(tmp_path: Path) -> None:
    """The default build path should not run package-maintenance preflight."""
    script = copy_script(tmp_path, "build")
    python_log = install_python_stub(tmp_path)
    preflight_log = tmp_path / "preflight.log"
    preflight = tmp_path / "scripts" / "esphome-preflight"
    preflight.write_text(
        f"#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> {preflight_log}\n",
        encoding="utf-8",
    )
    preflight.chmod(0o755)

    result = run_script(script)

    assert result.returncode == 0, result.stderr
    assert python_log.read_text(encoding="utf-8").splitlines() == [
        "-m esphome config garage-rtl433.yaml",
        "-m esphome compile garage-rtl433.yaml",
    ]
    assert not preflight_log.exists()


def test_build_preflight_forwards_global_update(tmp_path: Path) -> None:
    """The build wrapper should pass global update requests to preflight."""
    script = copy_script(tmp_path, "build")
    install_python_stub(tmp_path)
    preflight_log = tmp_path / "preflight.log"
    preflight = tmp_path / "scripts" / "esphome-preflight"
    preflight.write_text(
        f"#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> {preflight_log}\n",
        encoding="utf-8",
    )
    preflight.chmod(0o755)

    result = run_script(script, "--preflight", "--update-global")

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "python.log").read_text(encoding="utf-8").splitlines() == [
        "-m esphome config garage-rtl433.yaml",
        "-m esphome compile --only-generate garage-rtl433.yaml",
        "-m esphome compile garage-rtl433.yaml",
    ]
    assert preflight_log.read_text(encoding="utf-8").splitlines() == ["--update-global"]


def test_build_preflight_runs_without_extra_args(tmp_path: Path) -> None:
    """The preflight build path should work without optional preflight args."""
    script = copy_script(tmp_path, "build")
    install_python_stub(tmp_path)
    preflight_log = tmp_path / "preflight.log"
    preflight = tmp_path / "scripts" / "esphome-preflight"
    preflight.write_text(
        f"#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> {preflight_log}\n",
        encoding="utf-8",
    )
    preflight.chmod(0o755)

    result = run_script(script, "--preflight")

    assert result.returncode == 0, result.stderr
    assert preflight_log.read_text(encoding="utf-8").splitlines() == [""]


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
