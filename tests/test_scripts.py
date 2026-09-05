"""Regression tests for repository shell scripts."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import os
from pathlib import Path
import runpy
import shlex
import shutil
import subprocess
from typing import cast

import pytest

REPO_ROOT: Path = Path(__file__).resolve().parents[1]
PLATFORMIO_SCRIPT_ROOT: Path = REPO_ROOT / "scripts" / "platformio"
FIRMWARE_CONFIG = "rtl433-esphome-heltec-lora-32-v2.yaml"


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


def install_python_stub(
    tmp_path: Path,
    generated_platformio_ini: Path | None = None,
    generated_firmware: Path | None = None,
    generated_component_ref: str = "latest",
) -> Path:
    """Install a fake venv Python executable that logs invocations.

    Args:
        tmp_path: Temporary repository root.
        generated_platformio_ini: Optional PlatformIO config to create when
            the fake ESPHome command generates build files.
        generated_firmware: Optional firmware file to create when the fake
            ESPHome command compiles.
        generated_component_ref: Component ref expected for the fake ESPHome
            command that generates build files.

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
                (
                    'if [[ "$*" == '
                    f'"-m esphome -s rtl433_esphome_ref {generated_component_ref} '
                    f'compile --only-generate {FIRMWARE_CONFIG}" ]]; then'
                ),
                f"  mkdir -p {shlex.quote(str(generated_platformio_ini.parent))}",
                (
                    "  printf '%s\\n' "
                    "'platform=https://example.invalid/generated.zip' "
                    f"> {shlex.quote(str(generated_platformio_ini))}"
                ),
                "fi",
            ]
        )
    if generated_firmware is not None:
        script_lines.extend(
            [
                'if [[ "$*" == *" compile "* ]]; then',
                f"  mkdir -p {shlex.quote(str(generated_firmware.parent))}",
                f"  printf 'firmware' > {shlex.quote(str(generated_firmware))}",
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


def run_script(
    script: Path, *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run a copied shell script from its temporary repo root.

    Args:
        script: Script path under the temporary repo root.
        *args: Arguments to pass to the script.
        env: Optional extra environment variables.

    Returns:
        Completed process for assertions.
    """
    return subprocess.run(
        [str(script), *args],
        cwd=script.parents[1],
        check=False,
        text=True,
        capture_output=True,
        env={**os.environ, **(env or {})},
    )


def read_logged_arguments(log_path: Path) -> list[list[str]]:
    """Parse shell-escaped command arguments recorded by a test stub.

    Args:
        log_path: Invocation log written by a fake executable.

    Returns:
        One parsed argument list per invocation.
    """
    return [shlex.split(line) for line in log_path.read_text(encoding="utf-8").splitlines()]


def has_option(command: list[str], option: str, value: str) -> bool:
    """Return whether a command contains one option/value pair.

    Args:
        command: Parsed command arguments.
        option: Option name to find.
        value: Required option value.

    Returns:
        Whether the pair appears as adjacent command arguments.
    """
    return any(command[index : index + 2] == [option, value] for index in range(len(command) - 1))


def assert_esphome_invocations(
    log_path: Path,
    source_options: Mapping[str, str],
    expected_actions: Mapping[str, int],
) -> list[list[str]]:
    """Assert semantic ESPHome actions without snapshotting the whole command line.

    Args:
        log_path: Invocation log written by the fake ESPHome executable.
        source_options: Component source options that must reach ESPHome.
        expected_actions: Action names and expected invocation counts.

    Returns:
        Parsed ESPHome command arguments for any follow-up assertions.
    """
    commands = read_logged_arguments(log_path)
    assert len(commands) == sum(expected_actions.values())
    for command in commands:
        assert has_option(command, "-m", "esphome")
        assert FIRMWARE_CONFIG in command
        for option, value in source_options.items():
            assert has_option(command, "-s", option)
            option_index = command.index(option)
            assert command[option_index + 1] == value
        if "rtl433_esphome_url" not in source_options:
            assert not has_option(command, "-s", "rtl433_esphome_url")
        assert any(action in command for action in expected_actions)
    for action, count in expected_actions.items():
        assert sum(action in command for command in commands) == count
    return commands


class FakePlatformIOEnv:
    """Test double for PlatformIO's SCons environment."""

    def __init__(self) -> None:
        """Initialize recorded build middleware callbacks."""

        self.build_middlewares: list[Callable[[object], object | None]] = []

    def AddBuildMiddleware(self, callback: Callable[[object], object | None]) -> None:
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
    script = PLATFORMIO_SCRIPT_ROOT / script_name
    namespace = runpy.run_path(
        str(script),
        init_globals={"Import": lambda *_args: None, "env": fake_env},
    )
    return namespace, fake_env


def test_rtl433_esp_prebuild_skips_duplicate_decoder_source() -> None:
    """rtl_433_ESP v0.5.1 should not compile its duplicate decoder utility file."""
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
    assert_esphome_invocations(
        python_log,
        {"rtl433_esphome_ref": "latest"},
        {"config": 1, "compile": 1},
    )
    assert not preflight_log.exists()


@pytest.mark.parametrize(
    ("env", "source_options"),
    [
        pytest.param(
            {"RTL433_ESPHOME_REF": "v1.2.3"},
            {"rtl433_esphome_ref": "v1.2.3"},
            id="component-ref",
        ),
        pytest.param(
            {
                "RTL433_ESPHOME_URL": "https://github.com/example/rtl433_esphome.git",
                "RTL433_ESPHOME_REF": "abc123",
            },
            {
                "rtl433_esphome_url": "https://github.com/example/rtl433_esphome.git",
                "rtl433_esphome_ref": "abc123",
            },
            id="component-url",
        ),
    ],
)
def test_build_accepts_explicit_component_source(
    tmp_path: Path, env: dict[str, str], source_options: dict[str, str]
) -> None:
    """Explicit component source settings should be passed through to ESPHome."""
    script = copy_script(tmp_path, "build")
    python_log = install_python_stub(tmp_path)

    result = run_script(script, env=env)

    assert result.returncode == 0, result.stderr
    assert_esphome_invocations(python_log, source_options, {"config": 1, "compile": 1})


def test_build_exports_firmware_from_external_config_root(tmp_path: Path) -> None:
    """Release builds should export firmware rooted beside their temporary config."""
    script = copy_script(tmp_path, "build")
    config_dir = tmp_path / "runner-temp"
    config_dir.mkdir()
    config = config_dir / "release-firmware.yaml"
    config.write_text("esphome:\n  name: release-test\n", encoding="utf-8")
    firmware = config_dir / ".esphome" / "build" / "release-test" / "firmware.bin"
    install_python_stub(tmp_path, generated_firmware=firmware)
    output = config_dir / "firmware-path"

    result = run_script(
        script,
        "--firmware-output",
        str(output),
        env={"FIRMWARE_CONFIG": str(config)},
    )

    assert result.returncode == 0, result.stderr
    assert output.read_text(encoding="utf-8") == f"{firmware}\n"


@pytest.mark.parametrize("firmware_count", [0, 2])
def test_build_rejects_ambiguous_firmware_output(tmp_path: Path, firmware_count: int) -> None:
    """Release builds should fail closed unless exactly one firmware file exists."""
    script = copy_script(tmp_path, "build")
    config_dir = tmp_path / "runner-temp"
    config_dir.mkdir()
    config = config_dir / "release-firmware.yaml"
    config.write_text("esphome:\n  name: release-test\n", encoding="utf-8")
    generated_firmware = (
        config_dir / ".esphome" / "build" / "release-test" / "firmware.bin"
        if firmware_count
        else None
    )
    install_python_stub(tmp_path, generated_firmware=generated_firmware)
    if firmware_count == 2:
        second = config_dir / ".esphome" / "build" / "other-test" / "firmware.bin"
        second.parent.mkdir(parents=True)
        second.write_bytes(b"other firmware")

    result = run_script(
        script,
        "--firmware-output",
        str(config_dir / "firmware-path"),
        env={"FIRMWARE_CONFIG": str(config)},
    )

    assert result.returncode == 1
    assert f"found {firmware_count}" in result.stderr


@pytest.mark.parametrize(
    ("extra_args", "update_global"),
    [
        (("--update-global",), True),
        ((), False),
    ],
)
def test_build_preflight_modes(
    tmp_path: Path, extra_args: tuple[str, ...], update_global: bool
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
    esphome_commands = assert_esphome_invocations(
        tmp_path / "python.log",
        {"rtl433_esphome_ref": "latest"},
        {"config": 1, "compile": 2},
    )
    assert sum("--only-generate" in command for command in esphome_commands) == 1
    assert sum("--only-generate" not in command for command in esphome_commands) == 2
    preflight_commands = read_logged_arguments(preflight_log)
    assert len(preflight_commands) == 1
    assert str(generated_platformio_ini) in preflight_commands[0]
    assert ("--update-global" in preflight_commands[0]) is update_global


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
    commands = read_logged_arguments(python_log)
    assert len(commands) == 1
    assert has_option(commands[0], "-m", "platformio")
    assert "pkg" in commands[0]
    assert "install" in commands[0]
    assert "-g" in commands[0]
    assert "-f" in commands[0]
    assert has_option(commands[0], "-p", "https://example.invalid/platform-espressif32.zip")
