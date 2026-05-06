# RTL_433 ESPHome Hybrid Gateway Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an ESPHome native replacement for the garage OpenMQTTGateway `rtl_433` receiver, with four stable fridge/freezer entities and a bounded discovery workflow for rebinding sensors after battery changes.

**Architecture:** Keep the radio callback close to the proven `mag1024/esphome-rtl433` shape: `rtl_433_ESP` receives packets, ESPHome JSON parsing normalizes them, and a small pure C++ state layer handles matching, stale tracking, and discovery candidates. ESPHome codegen exposes native sensors, diagnostics, discovery controls, and OTA stop/status actions.

**Tech Stack:** ESPHome 2026.x external component, ESP32 Arduino framework, `rtl_433_ESP`, `RadioLib`, C++17, pytest-based host tests compiled with the system C++ compiler, `uv`, `ruff`, `mypy`.

---

## References

- Approved spec: `docs/superpowers/specs/2026-05-06-rtl433-esphome-hybrid-design.md`
- ESPHome component architecture: https://developers.esphome.io/architecture/components/
- ESPHome external components: https://esphome.io/components/external_components.html
- ESPHome template text for runtime mapping overrides: https://esphome.io/components/text/template/
- ESPHome text sensors: https://esphome.io/components/text_sensor/
- ESPHome sensors: https://esphome.io/components/sensor/
- ESPHome buttons: https://esphome.io/components/button/
- ESPHome globals: https://www.esphome.io/components/globals/
- `rtl_433_ESP`: https://github.com/NorthernMan54/rtl_433_ESP
- ESPHome `rtl_433_ESP` reference component: https://github.com/mag1024/esphome-rtl433

## File Structure

- `pyproject.toml`: Python tooling, pytest, ruff, mypy, and project metadata.
- `.pre-commit-config.yaml`: `prek` hook config for ruff and basic file hygiene.
- `scripts/test`: repo-native test runner that uses `./.venv`.
- `scripts/lint`: repo-native lint runner that uses `./.venv`.
- `components/rtl433_native/__init__.py`: ESPHome codegen schema, C++ variable creation, entity wiring, and custom actions.
- `components/rtl433_native/rtl433_native.h`: ESPHome component class and `rtl_433_ESP` adapter.
- `components/rtl433_native/rtl433_native.cpp`: ESPHome runtime setup, loop, JSON parsing, entity publishing, diagnostics, and OTA stop/status handlers.
- `components/rtl433_native/rtl433_state.h`: Pure C++ structs and state-machine declarations with no ESPHome includes.
- `components/rtl433_native/rtl433_state.cpp`: Pure C++ mapping, candidate-table, and stale-state logic.
- `garage-rtl433.yaml`: ESPHome firmware config for the Heltec/LoRa32-class receiver.
- `tests/conftest.py`: pytest fixture that compiles and runs C++ host tests.
- `tests/test_cpp_state.py`: pytest wrapper that invokes the C++ host test binary.
- `tests/cpp/test_rtl433_state.cpp`: host tests for mapping, candidates, overrides, formatting, and stale behavior.
- `README.md`: build, flash, discovery, rebinding, and HA migration runbook.
- `MEMORY.md`: update with implementation milestones and validated assumptions.

The pure C++ state layer is intentionally separate from ESPHome. That keeps the packet matching and candidate behavior testable on the host without building firmware for each logic change.

---

### Task 1: Tooling And Test Harness

**Files:**
- Create: `pyproject.toml`
- Create: `.pre-commit-config.yaml`
- Create: `scripts/test`
- Create: `scripts/lint`
- Create: `tests/conftest.py`

- [ ] **Step 1: Add Python project tooling**

Create directories:

```bash
mkdir -p scripts tests/cpp
```

Expected: no output.

Create `pyproject.toml`:

```toml
[project]
name = "rtl433-esphome"
version = "0.1.0"
description = "ESPHome rtl_433 native gateway for garage fridge and freezer sensors"
requires-python = ">=3.12"
dependencies = []

[dependency-groups]
dev = [
  "mypy>=1.18.0",
  "pytest>=8.4.0",
  "ruff>=0.15.0",
]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["B", "E", "F", "I", "N", "UP"]

[tool.mypy]
python_version = "3.12"
strict = true
files = ["tests"]
```

- [ ] **Step 2: Add `prek` config**

Create `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.15.12
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
```

- [ ] **Step 3: Add repo-native test runner**

Create `scripts/test`:

```bash
#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
./.venv/bin/python -m pytest "$@"
```

- [ ] **Step 4: Add repo-native lint runner**

Create `scripts/lint`:

```bash
#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
./.venv/bin/ruff check .
./.venv/bin/ruff format --check .
./.venv/bin/mypy
```

- [ ] **Step 5: Add C++ compile fixture**

Create `tests/conftest.py`:

```python
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
```

- [ ] **Step 6: Make scripts executable**

Run:

```bash
chmod +x scripts/test scripts/lint
```

Expected: no output.

- [ ] **Step 7: Install tooling**

Run:

```bash
uv venv .venv
uv sync --group dev
```

Expected: a local `.venv` is created and dev dependencies install successfully.

- [ ] **Step 8: Verify there are no tests yet**

Run:

```bash
./scripts/test
```

Expected: pytest exits with code `5` and reports `no tests ran`.

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml .pre-commit-config.yaml scripts/test scripts/lint tests/conftest.py
git commit -m "chore: add tooling for rtl433 gateway"
```

---

### Task 2: Pure C++ Mapping Model

**Files:**
- Create: `components/rtl433_native/rtl433_state.h`
- Create: `components/rtl433_native/rtl433_state.cpp`
- Create: `tests/cpp/test_rtl433_state.cpp`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Write failing tests for key parsing and known packet matching**

Create `tests/cpp/test_rtl433_state.cpp`:

```cpp
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <string>

#include "components/rtl433_native/rtl433_state.h"

namespace {

void require(bool condition, const std::string &message) {
  if (!condition) {
    std::cerr << message << '\n';
    std::exit(1);
  }
}

void test_key_parsing() {
  auto key = rtl433_native::parse_sensor_key("LaCrosse-TX141THBv2/0/203");
  require(key.has_value(), "expected valid LaCrosse key");
  require(key->model == "LaCrosse-TX141THBv2", "wrong parsed model");
  require(key->channel == "0", "wrong parsed channel");
  require(key->id == "203", "wrong parsed id");
  require(!rtl433_native::parse_sensor_key("LaCrosse-TX141THBv2/203").has_value(),
          "expected malformed key to fail");
}

void test_known_packet_updates_logical_sensor() {
  rtl433_native::GatewayState state;
  state.set_mapping("garage_combo_fridge", "LaCrosse-TX141THBv2/0/203");

  rtl433_native::DecodedPacket packet;
  packet.model = "LaCrosse-TX141THBv2";
  packet.channel = "0";
  packet.id = "203";
  packet.temperature_f = 34.16f;
  packet.humidity = 10.0f;
  packet.battery = 100.0f;
  packet.rssi = -70;
  packet.seen_ms = 1000;

  auto result = state.process_packet(packet);
  require(result == rtl433_native::PacketResult::MATCHED_KNOWN, "expected known packet match");

  const auto *logical = state.logical_sensor("garage_combo_fridge");
  require(logical != nullptr, "expected logical sensor state");
  require(std::fabs(logical->temperature_f - 34.16f) < 0.001f, "wrong temperature");
  require(logical->last_seen_ms == 1000, "wrong last seen timestamp");
}

}  // namespace

int main() {
  test_key_parsing();
  test_known_packet_updates_logical_sensor();
  return 0;
}
```

- [ ] **Step 2: Add pytest wrapper for the C++ test**

Modify `tests/conftest.py` only if the fixture does not already compile `tests/cpp/test_rtl433_state.cpp`. Then create `tests/test_cpp_state.py`:

```python
"""Host tests for the pure C++ rtl433 gateway state layer."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path


def test_rtl433_state_cpp(
    compile_and_run_cpp: Callable[[Path], subprocess.CompletedProcess[str]],
) -> None:
    """Compile and run the C++ state test binary."""

    source = Path(__file__).resolve().parent / "cpp/test_rtl433_state.cpp"
    result = compile_and_run_cpp(source)
    assert result.returncode == 0, result.stderr + result.stdout
```

- [ ] **Step 3: Run test to verify it fails**

Run:

```bash
./scripts/test tests/test_cpp_state.py -v
```

Expected: FAIL during compilation because `components/rtl433_native/rtl433_state.h` does not exist.

- [ ] **Step 4: Add pure state declarations**

Create `components/rtl433_native/rtl433_state.h`:

```cpp
#pragma once

#include <cmath>
#include <cstdint>
#include <optional>
#include <string>
#include <unordered_map>
#include <vector>

namespace rtl433_native {

struct SensorKey {
  std::string model;
  std::string channel;
  std::string id;
};

struct DecodedPacket {
  std::string model;
  std::string channel;
  std::string id;
  float temperature_f{NAN};
  float humidity{NAN};
  float battery{NAN};
  int rssi{0};
  uint32_t seen_ms{0};
};

struct LogicalSensorState {
  bool has_value{false};
  float temperature_f{NAN};
  float humidity{NAN};
  float battery{NAN};
  int rssi{0};
  uint32_t last_seen_ms{0};
};

enum class PacketResult {
  MATCHED_KNOWN,
  RECORDED_CANDIDATE,
  IGNORED_UNKNOWN,
  REJECTED_INVALID,
};

std::optional<SensorKey> parse_sensor_key(const std::string &value);
std::string format_sensor_key(const SensorKey &key);
bool matches_key(const DecodedPacket &packet, const SensorKey &key);

class GatewayState {
 public:
  void set_mapping(const std::string &logical_key, const std::string &sensor_key);
  const LogicalSensorState *logical_sensor(const std::string &logical_key) const;
  PacketResult process_packet(const DecodedPacket &packet);

 private:
  std::unordered_map<std::string, SensorKey> mappings_{};
  std::unordered_map<std::string, LogicalSensorState> logical_states_{};
};

}  // namespace rtl433_native
```

- [ ] **Step 5: Add minimal implementation**

Create `components/rtl433_native/rtl433_state.cpp`:

```cpp
#include "rtl433_state.h"

#include <cmath>
#include <sstream>

namespace rtl433_native {

std::optional<SensorKey> parse_sensor_key(const std::string &value) {
  std::stringstream stream(value);
  std::string model;
  std::string channel;
  std::string id;
  std::string extra;

  if (!std::getline(stream, model, '/') || !std::getline(stream, channel, '/') ||
      !std::getline(stream, id, '/') || std::getline(stream, extra, '/')) {
    return std::nullopt;
  }
  if (model.empty() || channel.empty() || id.empty()) {
    return std::nullopt;
  }
  return SensorKey{model, channel, id};
}

std::string format_sensor_key(const SensorKey &key) {
  return key.model + "/" + key.channel + "/" + key.id;
}

bool matches_key(const DecodedPacket &packet, const SensorKey &key) {
  return packet.model == key.model && packet.channel == key.channel && packet.id == key.id;
}

void GatewayState::set_mapping(const std::string &logical_key, const std::string &sensor_key) {
  auto parsed = parse_sensor_key(sensor_key);
  if (!parsed.has_value()) {
    return;
  }
  mappings_[logical_key] = *parsed;
  logical_states_.try_emplace(logical_key);
}

const LogicalSensorState *GatewayState::logical_sensor(const std::string &logical_key) const {
  auto item = logical_states_.find(logical_key);
  if (item == logical_states_.end()) {
    return nullptr;
  }
  return &item->second;
}

PacketResult GatewayState::process_packet(const DecodedPacket &packet) {
  if (packet.model.empty() || packet.id.empty()) {
    return PacketResult::REJECTED_INVALID;
  }

  for (const auto &[logical_key, sensor_key] : mappings_) {
    if (!matches_key(packet, sensor_key)) {
      continue;
    }
    auto &state = logical_states_[logical_key];
    state.has_value = true;
    state.temperature_f = packet.temperature_f;
    state.humidity = packet.humidity;
    state.battery = packet.battery;
    state.rssi = packet.rssi;
    state.last_seen_ms = packet.seen_ms;
    return PacketResult::MATCHED_KNOWN;
  }

  return PacketResult::IGNORED_UNKNOWN;
}

}  // namespace rtl433_native
```

- [ ] **Step 6: Run test to verify it passes**

Run:

```bash
./scripts/test tests/test_cpp_state.py -v
```

Expected: PASS.

- [ ] **Step 7: Run lint**

Run:

```bash
./scripts/lint
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add components/rtl433_native/rtl433_state.h components/rtl433_native/rtl433_state.cpp tests/conftest.py tests/test_cpp_state.py tests/cpp/test_rtl433_state.cpp
git commit -m "feat: add rtl433 mapping state"
```

---

### Task 3: Candidate Table, Discovery Mode, Overrides, And Stale Status

**Files:**
- Modify: `components/rtl433_native/rtl433_state.h`
- Modify: `components/rtl433_native/rtl433_state.cpp`
- Modify: `tests/cpp/test_rtl433_state.cpp`

- [ ] **Step 1: Add failing tests for discovery candidates**

Append these functions to `tests/cpp/test_rtl433_state.cpp` before `main()` and call them from `main()`:

```cpp
void test_unknowns_only_record_when_discovery_enabled() {
  rtl433_native::GatewayState state;
  state.set_candidate_limit(10);

  rtl433_native::DecodedPacket packet;
  packet.model = "Acurite-986";
  packet.channel = "1R";
  packet.id = "11932";
  packet.temperature_f = 75.0f;
  packet.battery = 100.0f;
  packet.rssi = -88;
  packet.seen_ms = 2000;

  require(state.process_packet(packet) == rtl433_native::PacketResult::IGNORED_UNKNOWN,
          "unknown packet should be ignored while discovery is disabled");
  require(state.candidates().empty(), "candidate table should be empty");

  state.set_discovery_enabled(true);
  require(state.process_packet(packet) == rtl433_native::PacketResult::RECORDED_CANDIDATE,
          "unknown packet should be recorded while discovery is enabled");
  require(state.candidates().size() == 1, "candidate table should have one row");
  require(state.candidates().front().packet_count == 1, "candidate count should start at one");
}

void test_candidates_are_grouped_capped_and_clearable() {
  rtl433_native::GatewayState state;
  state.set_discovery_enabled(true);
  state.set_candidate_limit(2);

  for (int index = 0; index < 3; ++index) {
    rtl433_native::DecodedPacket packet;
    packet.model = "Noise";
    packet.channel = std::to_string(index);
    packet.id = std::to_string(100 + index);
    packet.temperature_f = static_cast<float>(index);
    packet.rssi = -60 - index;
    packet.seen_ms = 1000 + static_cast<uint32_t>(index);
    state.process_packet(packet);
  }

  require(state.candidates().size() == 2, "candidate table should honor limit");
  require(state.candidates().front().last_seen_ms == 1002, "newest candidate should sort first");

  state.clear_candidates();
  require(state.candidates().empty(), "clear should empty candidate table");
}

void test_mapping_override_replaces_default_key() {
  rtl433_native::GatewayState state;
  state.set_mapping("garage_freezer_1", "Acurite-986/1R/11932");
  state.set_mapping("garage_freezer_1", "Acurite-986/1R/55555");

  rtl433_native::DecodedPacket old_packet;
  old_packet.model = "Acurite-986";
  old_packet.channel = "1R";
  old_packet.id = "11932";
  old_packet.temperature_f = 75.0f;
  old_packet.seen_ms = 1000;
  require(state.process_packet(old_packet) == rtl433_native::PacketResult::IGNORED_UNKNOWN,
          "old mapping should no longer match");

  rtl433_native::DecodedPacket new_packet = old_packet;
  new_packet.id = "55555";
  new_packet.temperature_f = 10.0f;
  new_packet.seen_ms = 2000;
  require(state.process_packet(new_packet) == rtl433_native::PacketResult::MATCHED_KNOWN,
          "new mapping should match");
}

void test_stale_detection_uses_last_seen() {
  rtl433_native::GatewayState state;
  state.set_stale_after_ms(600000);
  state.set_mapping("garage_combo_freezer", "TFA-303221/2/88");

  rtl433_native::DecodedPacket packet;
  packet.model = "TFA-303221";
  packet.channel = "2";
  packet.id = "88";
  packet.temperature_f = 1.22f;
  packet.seen_ms = 1000;
  state.process_packet(packet);

  require(!state.is_stale("garage_combo_freezer", 600999), "sensor should not be stale yet");
  require(state.is_stale("garage_combo_freezer", 601001), "sensor should be stale after threshold");
}
```

Update `main()`:

```cpp
int main() {
  test_key_parsing();
  test_known_packet_updates_logical_sensor();
  test_unknowns_only_record_when_discovery_enabled();
  test_candidates_are_grouped_capped_and_clearable();
  test_mapping_override_replaces_default_key();
  test_stale_detection_uses_last_seen();
  return 0;
}
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
./scripts/test tests/test_cpp_state.py -v
```

Expected: FAIL during compilation because candidate and stale methods are not declared.

- [ ] **Step 3: Extend state declarations**

Add to `components/rtl433_native/rtl433_state.h`:

```cpp
struct CandidateRow {
  SensorKey key;
  float temperature_f{NAN};
  float humidity{NAN};
  float battery{NAN};
  int rssi{0};
  uint32_t first_seen_ms{0};
  uint32_t last_seen_ms{0};
  uint32_t packet_count{0};
  bool matched_known{false};
};

std::string format_candidate(const CandidateRow &candidate);
```

Add these public methods to `GatewayState`:

```cpp
void set_discovery_enabled(bool enabled) { discovery_enabled_ = enabled; }
bool discovery_enabled() const { return discovery_enabled_; }
void set_candidate_limit(std::size_t limit) { candidate_limit_ = limit; }
void set_stale_after_ms(uint32_t stale_after_ms) { stale_after_ms_ = stale_after_ms; }
void clear_candidates() { candidates_.clear(); }
const std::vector<CandidateRow> &candidates() const { return candidates_; }
bool is_stale(const std::string &logical_key, uint32_t now_ms) const;
```

Add these private fields:

```cpp
bool discovery_enabled_{false};
std::size_t candidate_limit_{10};
uint32_t stale_after_ms_{3600000};
std::vector<CandidateRow> candidates_{};
void record_candidate(const DecodedPacket &packet, bool matched_known);
```

- [ ] **Step 4: Implement candidate and stale behavior**

Add to `components/rtl433_native/rtl433_state.cpp`:

```cpp
#include <algorithm>
```

Add these functions:

```cpp
std::string format_candidate(const CandidateRow &candidate) {
  std::string value = format_sensor_key(candidate.key);
  value += " temp=" + std::to_string(candidate.temperature_f);
  value += " hum=" + std::to_string(candidate.humidity);
  value += " batt=" + std::to_string(candidate.battery);
  value += " rssi=" + std::to_string(candidate.rssi);
  value += " first=" + std::to_string(candidate.first_seen_ms);
  value += " last=" + std::to_string(candidate.last_seen_ms);
  value += " count=" + std::to_string(candidate.packet_count);
  value += candidate.matched_known ? " matched=1" : " matched=0";
  return value;
}

bool GatewayState::is_stale(const std::string &logical_key, uint32_t now_ms) const {
  const auto *state = logical_sensor(logical_key);
  if (state == nullptr || !state->has_value) {
    return true;
  }
  return now_ms > state->last_seen_ms && now_ms - state->last_seen_ms > stale_after_ms_;
}

void GatewayState::record_candidate(const DecodedPacket &packet, bool matched_known) {
  SensorKey key{packet.model, packet.channel, packet.id};
  const std::string formatted = format_sensor_key(key);

  auto existing = std::find_if(candidates_.begin(), candidates_.end(), [&](const CandidateRow &row) {
    return format_sensor_key(row.key) == formatted;
  });

  if (existing == candidates_.end()) {
    CandidateRow row;
    row.key = key;
    row.first_seen_ms = packet.seen_ms;
    candidates_.push_back(row);
    existing = std::prev(candidates_.end());
  }

  existing->temperature_f = packet.temperature_f;
  existing->humidity = packet.humidity;
  existing->battery = packet.battery;
  existing->rssi = packet.rssi;
  existing->last_seen_ms = packet.seen_ms;
  existing->packet_count += 1;
  existing->matched_known = matched_known;

  std::sort(candidates_.begin(), candidates_.end(), [](const CandidateRow &left, const CandidateRow &right) {
    return left.last_seen_ms > right.last_seen_ms;
  });

  if (candidates_.size() > candidate_limit_) {
    candidates_.resize(candidate_limit_);
  }
}
```

Change `process_packet()` so matched packets call `record_candidate(packet, true)` only when discovery is enabled, and unmatched valid packets return `RECORDED_CANDIDATE` only when discovery is enabled:

```cpp
PacketResult GatewayState::process_packet(const DecodedPacket &packet) {
  if (packet.model.empty() || packet.id.empty()) {
    return PacketResult::REJECTED_INVALID;
  }

  for (const auto &[logical_key, sensor_key] : mappings_) {
    if (!matches_key(packet, sensor_key)) {
      continue;
    }
    auto &state = logical_states_[logical_key];
    state.has_value = true;
    state.temperature_f = packet.temperature_f;
    state.humidity = packet.humidity;
    state.battery = packet.battery;
    state.rssi = packet.rssi;
    state.last_seen_ms = packet.seen_ms;
    if (discovery_enabled_) {
      record_candidate(packet, true);
    }
    return PacketResult::MATCHED_KNOWN;
  }

  if (discovery_enabled_) {
    record_candidate(packet, false);
    return PacketResult::RECORDED_CANDIDATE;
  }

  return PacketResult::IGNORED_UNKNOWN;
}
```

- [ ] **Step 5: Run test to verify it passes**

Run:

```bash
./scripts/test tests/test_cpp_state.py -v
```

Expected: PASS.

- [ ] **Step 6: Run lint**

Run:

```bash
./scripts/lint
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add components/rtl433_native/rtl433_state.h components/rtl433_native/rtl433_state.cpp tests/cpp/test_rtl433_state.cpp
git commit -m "feat: add rtl433 discovery state"
```

---

### Task 4: ESPHome Codegen Schema And Actions

**Files:**
- Create: `components/rtl433_native/__init__.py`
- Modify: `components/rtl433_native/rtl433_native.h`

- [ ] **Step 1: Write component schema**

Create `components/rtl433_native/__init__.py`:

```python
"""ESPHome codegen for the native rtl_433 gateway component."""

from __future__ import annotations

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome import automation
from esphome.components import binary_sensor, sensor, text_sensor
from esphome.const import CONF_ID

AUTO_LOAD = ["binary_sensor", "json", "sensor", "text_sensor"]
CODEOWNERS = ["@snuffy2"]

CONF_CANDIDATE_LIMIT = "candidate_limit"
CONF_CANDIDATES = "candidates"
CONF_BATTERY = "battery"
CONF_CHANNEL = "channel"
CONF_DISCOVERY_ENABLED = "discovery_enabled"
CONF_HUMIDITY = "humidity"
CONF_KEY = "key"
CONF_KNOWN_SENSORS = "known_sensors"
CONF_LAST_PACKET = "last_packet"
CONF_MODEL = "model"
CONF_PACKET_COUNT = "packet_count"
CONF_RF_ID = "rf_id"
CONF_RSSI = "rssi"
CONF_STALE = "stale"
CONF_STALE_AFTER = "stale_after"
CONF_TEMPERATURE = "temperature"
CONF_UNKNOWN_PACKET_COUNT = "unknown_packet_count"

rtl433_native_ns = cg.esphome_ns.namespace("rtl433_native")
Gateway = rtl433_native_ns.class_("Gateway", cg.Component)
StatusAction = rtl433_native_ns.class_("StatusAction", automation.Action)
StopAction = rtl433_native_ns.class_("StopAction", automation.Action)
ClearCandidatesAction = rtl433_native_ns.class_("ClearCandidatesAction", automation.Action)

SENSOR_ENTRY_SCHEMA = cv.Schema(
    {
        cv.Required(CONF_KEY): cv.string_strict,
        cv.Required(CONF_MODEL): cv.string_strict,
        cv.Required(CONF_CHANNEL): cv.string_strict,
        cv.Required(CONF_RF_ID): cv.string_strict,
        cv.Required(CONF_TEMPERATURE): sensor.sensor_schema(
            unit_of_measurement="°F",
            accuracy_decimals=2,
            device_class="temperature",
            state_class="measurement",
        ),
        cv.Optional(CONF_HUMIDITY): sensor.sensor_schema(
            unit_of_measurement="%",
            accuracy_decimals=0,
            device_class="humidity",
            state_class="measurement",
        ),
        cv.Optional(CONF_BATTERY): sensor.sensor_schema(
            unit_of_measurement="%",
            accuracy_decimals=0,
            device_class="battery",
            state_class="measurement",
        ),
        cv.Optional(CONF_RSSI): sensor.sensor_schema(
            unit_of_measurement="dB",
            accuracy_decimals=0,
            device_class="signal_strength",
            state_class="measurement",
        ),
        cv.Optional(CONF_STALE): binary_sensor.binary_sensor_schema(device_class="problem"),
    }
)

CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(): cv.declare_id(Gateway),
        cv.Required(CONF_KNOWN_SENSORS): cv.All(cv.ensure_list(SENSOR_ENTRY_SCHEMA), cv.Length(min=1)),
        cv.Optional(CONF_CANDIDATE_LIMIT, default=10): cv.int_range(min=1, max=20),
        cv.Optional(CONF_STALE_AFTER, default="1h"): cv.positive_time_period_milliseconds,
        cv.Optional(CONF_CANDIDATES, default=[]): cv.All(
            cv.ensure_list(text_sensor.text_sensor_schema(icon="mdi:radio-tower")),
            cv.Length(max=20),
        ),
        cv.Optional(CONF_LAST_PACKET): text_sensor.text_sensor_schema(icon="mdi:radio"),
        cv.Optional(CONF_PACKET_COUNT): sensor.sensor_schema(
            accuracy_decimals=0,
            state_class="total_increasing",
        ),
        cv.Optional(CONF_UNKNOWN_PACKET_COUNT): sensor.sensor_schema(
            accuracy_decimals=0,
            state_class="total_increasing",
        ),
        cv.Optional(CONF_DISCOVERY_ENABLED): binary_sensor.binary_sensor_schema(
            entity_category="diagnostic",
        ),
    }
).extend(cv.COMPONENT_SCHEMA)

GATEWAY_ID_SCHEMA = cv.Schema({cv.GenerateID(): cv.use_id(Gateway)})


async def to_code(config: dict) -> None:
    """Generate C++ for the rtl433_native component."""

    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    cg.add(var.set_candidate_limit(config[CONF_CANDIDATE_LIMIT]))
    cg.add(var.set_stale_after_ms(config[CONF_STALE_AFTER].total_milliseconds))

    for entry in config[CONF_KNOWN_SENSORS]:
        cg.add(var.add_mapping(entry[CONF_KEY], entry[CONF_MODEL], entry[CONF_CHANNEL], entry[CONF_RF_ID]))
        temperature = await sensor.new_sensor(entry[CONF_TEMPERATURE])
        cg.add(var.set_temperature_sensor(entry[CONF_KEY], temperature))
        if CONF_HUMIDITY in entry:
            humidity = await sensor.new_sensor(entry[CONF_HUMIDITY])
            cg.add(var.set_humidity_sensor(entry[CONF_KEY], humidity))
        if CONF_BATTERY in entry:
            battery = await sensor.new_sensor(entry[CONF_BATTERY])
            cg.add(var.set_battery_sensor(entry[CONF_KEY], battery))
        if CONF_RSSI in entry:
            rssi = await sensor.new_sensor(entry[CONF_RSSI])
            cg.add(var.set_rssi_sensor(entry[CONF_KEY], rssi))
        if CONF_STALE in entry:
            stale = await binary_sensor.new_binary_sensor(entry[CONF_STALE])
            cg.add(var.set_stale_sensor(entry[CONF_KEY], stale))

    for index, candidate_config in enumerate(config[CONF_CANDIDATES]):
        candidate = await text_sensor.new_text_sensor(candidate_config)
        cg.add(var.set_candidate_text_sensor(index, candidate))

    if CONF_LAST_PACKET in config:
        last_packet = await text_sensor.new_text_sensor(config[CONF_LAST_PACKET])
        cg.add(var.set_last_packet_sensor(last_packet))
    if CONF_PACKET_COUNT in config:
        packet_count = await sensor.new_sensor(config[CONF_PACKET_COUNT])
        cg.add(var.set_packet_count_sensor(packet_count))
    if CONF_UNKNOWN_PACKET_COUNT in config:
        unknown_count = await sensor.new_sensor(config[CONF_UNKNOWN_PACKET_COUNT])
        cg.add(var.set_unknown_packet_count_sensor(unknown_count))
    if CONF_DISCOVERY_ENABLED in config:
        discovery = await binary_sensor.new_binary_sensor(config[CONF_DISCOVERY_ENABLED])
        cg.add(var.set_discovery_enabled_sensor(discovery))


@automation.register_action(
    "rtl433_native.status",
    StatusAction,
    automation.maybe_simple_id(GATEWAY_ID_SCHEMA),
)
@automation.register_action(
    "rtl433_native.stop",
    StopAction,
    automation.maybe_simple_id(GATEWAY_ID_SCHEMA),
)
@automation.register_action(
    "rtl433_native.clear_candidates",
    ClearCandidatesAction,
    automation.maybe_simple_id(GATEWAY_ID_SCHEMA),
)
async def action_to_code(config, action_id, template_arg, args):
    """Generate automation action instances."""

    var = cg.new_Pvariable(action_id, template_arg)
    await cg.register_parented(var, config[CONF_ID])
    return var
```

- [ ] **Step 2: Add component method declarations**

Create `components/rtl433_native/rtl433_native.h` with declarations matching the codegen methods:

```cpp
#pragma once

#include <array>
#include <string>
#include <unordered_map>

#include "esphome/core/component.h"
#include "esphome/core/automation.h"
#include "esphome/components/binary_sensor/binary_sensor.h"
#include "esphome/components/sensor/sensor.h"
#include "esphome/components/text_sensor/text_sensor.h"

#include "rtl433_state.h"

#undef yield
#undef millis
#undef micros
#undef delay
#undef delayMicroseconds

#include "rtl_433_ESP.h"

namespace esphome::rtl433_native {

struct EntitySet {
  sensor::Sensor *temperature{nullptr};
  sensor::Sensor *humidity{nullptr};
  sensor::Sensor *battery{nullptr};
  sensor::Sensor *rssi{nullptr};
  binary_sensor::BinarySensor *stale{nullptr};
};

class Gateway : public Component {
 public:
  Gateway();

  void setup() override;
  void loop() override;
  void dump_config() override;

  void stop();
  void status();
  void clear_candidates();
  void set_discovery_enabled(bool enabled);
  void add_mapping(const std::string &logical_key, const std::string &model,
                   const std::string &channel, const std::string &id);
  void set_override(const std::string &logical_key, const std::string &sensor_key);
  void set_candidate_limit(std::size_t limit);
  void set_stale_after_ms(uint32_t stale_after_ms);
  void set_temperature_sensor(const std::string &logical_key, sensor::Sensor *sensor);
  void set_humidity_sensor(const std::string &logical_key, sensor::Sensor *sensor);
  void set_battery_sensor(const std::string &logical_key, sensor::Sensor *sensor);
  void set_rssi_sensor(const std::string &logical_key, sensor::Sensor *sensor);
  void set_stale_sensor(const std::string &logical_key, binary_sensor::BinarySensor *sensor);
  void set_candidate_text_sensor(std::size_t index, text_sensor::TextSensor *sensor);
  void set_last_packet_sensor(text_sensor::TextSensor *sensor);
  void set_packet_count_sensor(sensor::Sensor *sensor);
  void set_unknown_packet_count_sensor(sensor::Sensor *sensor);
  void set_discovery_enabled_sensor(binary_sensor::BinarySensor *sensor);

 protected:
  rtl_433_ESP rf_{};
  char buffer_[512]{};
  ::rtl433_native::GatewayState state_{};
  std::unordered_map<std::string, EntitySet> entities_{};
  std::array<text_sensor::TextSensor *, 20> candidate_sensors_{};
  text_sensor::TextSensor *last_packet_sensor_{nullptr};
  sensor::Sensor *packet_count_sensor_{nullptr};
  sensor::Sensor *unknown_packet_count_sensor_{nullptr};
  binary_sensor::BinarySensor *discovery_enabled_sensor_{nullptr};
  uint32_t packet_count_{0};
  uint32_t unknown_packet_count_{0};
  static Gateway *instance_;

  static void process_dispatch(char *message);
  void process_message(char *message);
  void publish_state(const std::string &logical_key);
  void publish_candidates();
  void publish_stale_states();
};

template <typename... Ts>
class StatusAction : public Action<Ts...>, public Parented<Gateway> {
 public:
  void play(Ts... x) override { this->parent_->status(); }
};

template <typename... Ts>
class StopAction : public Action<Ts...>, public Parented<Gateway> {
 public:
  void play(Ts... x) override { this->parent_->stop(); }
};

template <typename... Ts>
class ClearCandidatesAction : public Action<Ts...>, public Parented<Gateway> {
 public:
  void play(Ts... x) override { this->parent_->clear_candidates(); }
};

}  // namespace esphome::rtl433_native
```

- [ ] **Step 3: Commit**

```bash
git add components/rtl433_native/__init__.py components/rtl433_native/rtl433_native.h
git commit -m "feat: add rtl433 esphome codegen"
```

---

### Task 5: ESPHome Runtime Component

**Files:**
- Create: `components/rtl433_native/rtl433_native.cpp`
- Modify: `components/rtl433_native/rtl433_native.h`
- Modify: `components/rtl433_native/rtl433_state.h`
- Modify: `components/rtl433_native/rtl433_state.cpp`

- [ ] **Step 1: Add runtime implementation**

Create `components/rtl433_native/rtl433_native.cpp`:

```cpp
#include "rtl433_native.h"

#include "esphome/components/json/json_util.h"
#include "esphome/core/log.h"

namespace esphome::rtl433_native {

static const char *const TAG = "rtl433_native";

Gateway *Gateway::instance_ = nullptr;

Gateway::Gateway() { instance_ = this; }

void Gateway::setup() {
  this->rf_.initReceiver(RF_MODULE_RECEIVER_GPIO, RF_MODULE_FREQUENCY);
  this->rf_.setCallback(&Gateway::process_dispatch, this->buffer_, sizeof(this->buffer_));
  this->rf_.enableReceiver();
}

void Gateway::loop() {
  this->rf_.loop();
  this->publish_stale_states();
}

void Gateway::dump_config() {
  ESP_LOGCONFIG(TAG, "RTL433 native gateway");
  ESP_LOGCONFIG(TAG, "  Candidate limit: %u", static_cast<unsigned>(this->state_.candidates().capacity()));
}

void Gateway::stop() { this->rf_.disableReceiver(); }

void Gateway::status() {
  this->rf_.getStatus();
  this->rf_.getModuleStatus();
}

void Gateway::clear_candidates() {
  this->state_.clear_candidates();
  this->publish_candidates();
}

void Gateway::set_discovery_enabled(bool enabled) {
  this->state_.set_discovery_enabled(enabled);
  if (this->discovery_enabled_sensor_ != nullptr) {
    this->discovery_enabled_sensor_->publish_state(enabled);
  }
}

void Gateway::add_mapping(const std::string &logical_key, const std::string &model,
                          const std::string &channel, const std::string &id) {
  this->state_.set_mapping(logical_key, model + "/" + channel + "/" + id);
  this->entities_.try_emplace(logical_key);
}

void Gateway::set_override(const std::string &logical_key, const std::string &sensor_key) {
  this->state_.set_mapping(logical_key, sensor_key);
}

void Gateway::set_candidate_limit(std::size_t limit) { this->state_.set_candidate_limit(limit); }

void Gateway::set_stale_after_ms(uint32_t stale_after_ms) {
  this->state_.set_stale_after_ms(stale_after_ms);
}

void Gateway::set_temperature_sensor(const std::string &logical_key, sensor::Sensor *sensor) {
  this->entities_[logical_key].temperature = sensor;
}

void Gateway::set_humidity_sensor(const std::string &logical_key, sensor::Sensor *sensor) {
  this->entities_[logical_key].humidity = sensor;
}

void Gateway::set_battery_sensor(const std::string &logical_key, sensor::Sensor *sensor) {
  this->entities_[logical_key].battery = sensor;
}

void Gateway::set_rssi_sensor(const std::string &logical_key, sensor::Sensor *sensor) {
  this->entities_[logical_key].rssi = sensor;
}

void Gateway::set_stale_sensor(const std::string &logical_key, binary_sensor::BinarySensor *sensor) {
  this->entities_[logical_key].stale = sensor;
}

void Gateway::set_candidate_text_sensor(std::size_t index, text_sensor::TextSensor *sensor) {
  if (index < this->candidate_sensors_.size()) {
    this->candidate_sensors_[index] = sensor;
  }
}

void Gateway::set_last_packet_sensor(text_sensor::TextSensor *sensor) {
  this->last_packet_sensor_ = sensor;
}

void Gateway::set_packet_count_sensor(sensor::Sensor *sensor) { this->packet_count_sensor_ = sensor; }

void Gateway::set_unknown_packet_count_sensor(sensor::Sensor *sensor) {
  this->unknown_packet_count_sensor_ = sensor;
}

void Gateway::set_discovery_enabled_sensor(binary_sensor::BinarySensor *sensor) {
  this->discovery_enabled_sensor_ = sensor;
}

void Gateway::process_dispatch(char *message) {
  if (Gateway::instance_ != nullptr) {
    Gateway::instance_->process_message(message);
  }
}

void Gateway::process_message(char *message) {
  ESP_LOGD(TAG, "Received rtl_433 message: %s", message);
  json::parse_json(message, [this](JsonObject root) {
    const char *model = root["model"] | "";
    if (std::string(model) == "status") {
      return true;
    }

    ::rtl433_native::DecodedPacket packet;
    packet.model = model;
    packet.id = std::to_string(root["id"].as<int>());
    packet.channel = std::to_string(root["channel"].as<int>());
    packet.temperature_f = root["temperature_F"] | root["temperature_1_F"] | NAN;
    packet.humidity = root["humidity"] | NAN;
    packet.battery = root["battery_ok"].is<int>() ? root["battery_ok"].as<int>() * 100.0f : NAN;
    packet.rssi = root["rssi"] | 0;
    packet.seen_ms = millis();

    this->packet_count_ += 1;
    if (this->packet_count_sensor_ != nullptr) {
      this->packet_count_sensor_->publish_state(this->packet_count_);
    }

    const ::rtl433_native::PacketResult result = this->state_.process_packet(packet);
    if (this->last_packet_sensor_ != nullptr) {
      this->last_packet_sensor_->publish_state(
          ::rtl433_native::format_sensor_key({packet.model, packet.channel, packet.id}));
    }

    if (result == ::rtl433_native::PacketResult::MATCHED_KNOWN) {
      for (const auto &[logical_key, entities] : this->entities_) {
        const auto *logical = this->state_.logical_sensor(logical_key);
        if (logical != nullptr && logical->last_seen_ms == packet.seen_ms) {
          this->publish_state(logical_key);
        }
      }
    } else if (result == ::rtl433_native::PacketResult::RECORDED_CANDIDATE ||
               result == ::rtl433_native::PacketResult::IGNORED_UNKNOWN) {
      this->unknown_packet_count_ += 1;
      if (this->unknown_packet_count_sensor_ != nullptr) {
        this->unknown_packet_count_sensor_->publish_state(this->unknown_packet_count_);
      }
    }

    this->publish_candidates();
    return true;
  });
}

void Gateway::publish_state(const std::string &logical_key) {
  const auto entities_item = this->entities_.find(logical_key);
  const auto *logical = this->state_.logical_sensor(logical_key);
  if (entities_item == this->entities_.end() || logical == nullptr || !logical->has_value) {
    return;
  }

  const EntitySet &entities = entities_item->second;
  if (entities.temperature != nullptr) {
    entities.temperature->publish_state(logical->temperature_f);
  }
  if (entities.humidity != nullptr && !std::isnan(logical->humidity)) {
    entities.humidity->publish_state(logical->humidity);
  }
  if (entities.battery != nullptr && !std::isnan(logical->battery)) {
    entities.battery->publish_state(logical->battery);
  }
  if (entities.rssi != nullptr) {
    entities.rssi->publish_state(logical->rssi);
  }
  if (entities.stale != nullptr) {
    entities.stale->publish_state(false);
  }
}

void Gateway::publish_candidates() {
  const auto &candidates = this->state_.candidates();
  for (std::size_t index = 0; index < this->candidate_sensors_.size(); ++index) {
    auto *sensor = this->candidate_sensors_[index];
    if (sensor == nullptr) {
      continue;
    }
    if (index < candidates.size()) {
      sensor->publish_state(::rtl433_native::format_candidate(candidates[index]));
    } else {
      sensor->publish_state("");
    }
  }
}

void Gateway::publish_stale_states() {
  const uint32_t now = millis();
  for (auto &[logical_key, entities] : this->entities_) {
    if (entities.stale != nullptr) {
      entities.stale->publish_state(this->state_.is_stale(logical_key, now));
    }
  }
}

}  // namespace esphome::rtl433_native
```

- [ ] **Step 2: Add missing include for `std::isnan`**

Ensure `components/rtl433_native/rtl433_native.cpp` includes:

```cpp
#include <cmath>
```

- [ ] **Step 3: Fix channel extraction for string channels**

Replace the initial `packet.channel` line with logic that handles string channels such as `1R`:

```cpp
if (root["channel"].is<const char *>()) {
  packet.channel = root["channel"].as<const char *>();
} else if (root["channel"].is<int>()) {
  packet.channel = std::to_string(root["channel"].as<int>());
} else if (root["subtype"].is<const char *>()) {
  packet.channel = root["subtype"].as<const char *>();
} else {
  packet.channel = "0";
}
```

- [ ] **Step 4: Fix capacity logging**

Add `candidate_limit()` to `GatewayState`:

```cpp
std::size_t candidate_limit() const { return candidate_limit_; }
```

Replace the capacity log line:

```cpp
ESP_LOGCONFIG(TAG, "  Candidate limit: %u", static_cast<unsigned>(this->state_.candidate_limit()));
```

- [ ] **Step 5: Run host tests**

Run:

```bash
./scripts/test tests/test_cpp_state.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add components/rtl433_native/rtl433_native.cpp components/rtl433_native/rtl433_native.h components/rtl433_native/rtl433_state.h components/rtl433_native/rtl433_state.cpp
git commit -m "feat: add rtl433 esphome runtime"
```

---

### Task 6: ESPHome Firmware YAML

**Files:**
- Create: `garage-rtl433.yaml`
- Modify: `components/rtl433_native/__init__.py`

- [ ] **Step 1: Create firmware YAML with known mappings**

Create `garage-rtl433.yaml`:

```yaml
substitutions:
  device_name: garage-rtl433-native
  friendly_name: Garage RTL433 Native

esphome:
  name: ${device_name}
  friendly_name: ${friendly_name}
  comment: "Heltec WiFi LoRa 32 V2-style 433 MHz rtl_433 ESPHome gateway"
  libraries:
    - rtl_433_ESP=https://github.com/NorthernMan54/rtl_433_ESP.git
    - RadioLib@6.2.0
  platformio_options:
    lib_ldf_mode: "chain+"
    build_flags:
      - "-DONBOARD_LED=LED_BUILTIN"
      - "-DRF_SX1278"
      - "-DRF_MODULE_FREQUENCY=433.92"

esp32:
  board: heltec_wifi_kit_32_V2
  framework:
    type: arduino

logger:

api:

ota:
  - platform: esphome
    on_begin:
      - rtl433_native.stop: rtl433_gateway

wifi:
  ssid: !secret wifi_ssid
  password: !secret wifi_password
  ap:
    ssid: "${friendly_name} Fallback"
    password: !secret fallback_ap_password

captive_portal:

external_components:
  - source:
      type: local
      path: components

rtl433_native:
  id: rtl433_gateway
  candidate_limit: 10
  stale_after: 1h
  known_sensors:
    - key: garage_combo_fridge
      model: "LaCrosse-TX141THBv2"
      channel: "0"
      rf_id: "203"
      temperature:
        name: "Garage Combo Fridge"
      humidity:
        name: "Garage Combo Fridge Humidity"
        entity_category: diagnostic
      battery:
        name: "Garage Combo Fridge Battery"
        entity_category: diagnostic
      rssi:
        name: "Garage Combo Fridge RSSI"
        entity_category: diagnostic
      stale:
        name: "Garage Combo Fridge Stale"
        entity_category: diagnostic
    - key: garage_combo_freezer
      model: "TFA-303221"
      channel: "2"
      rf_id: "88"
      temperature:
        name: "Garage Combo Freezer"
      humidity:
        name: "Garage Combo Freezer Humidity"
        entity_category: diagnostic
      battery:
        name: "Garage Combo Freezer Battery"
        entity_category: diagnostic
      rssi:
        name: "Garage Combo Freezer RSSI"
        entity_category: diagnostic
      stale:
        name: "Garage Combo Freezer Stale"
        entity_category: diagnostic
    - key: garage_freezer_1
      model: "Acurite-986"
      channel: "1R"
      rf_id: "11932"
      temperature:
        name: "Garage Freezer 1"
      battery:
        name: "Garage Freezer 1 Battery"
        entity_category: diagnostic
      rssi:
        name: "Garage Freezer 1 RSSI"
        entity_category: diagnostic
      stale:
        name: "Garage Freezer 1 Stale"
        entity_category: diagnostic
    - key: garage_freezer_2
      model: "Acurite-986"
      channel: "2F"
      rf_id: "31274"
      temperature:
        name: "Garage Freezer 2"
      battery:
        name: "Garage Freezer 2 Battery"
        entity_category: diagnostic
      rssi:
        name: "Garage Freezer 2 RSSI"
        entity_category: diagnostic
      stale:
        name: "Garage Freezer 2 Stale"
        entity_category: diagnostic
  last_packet:
    name: "Garage RTL433 Last Packet"
    entity_category: diagnostic
  packet_count:
    name: "Garage RTL433 Packet Count"
    entity_category: diagnostic
  unknown_packet_count:
    name: "Garage RTL433 Unknown Packet Count"
    entity_category: diagnostic
  discovery_enabled:
    name: "Garage RTL433 Discovery Enabled"
  candidates:
    - name: "Garage RTL433 Candidate 1"
      entity_category: diagnostic
    - name: "Garage RTL433 Candidate 2"
      entity_category: diagnostic
    - name: "Garage RTL433 Candidate 3"
      entity_category: diagnostic
    - name: "Garage RTL433 Candidate 4"
      entity_category: diagnostic
    - name: "Garage RTL433 Candidate 5"
      entity_category: diagnostic
    - name: "Garage RTL433 Candidate 6"
      entity_category: diagnostic
    - name: "Garage RTL433 Candidate 7"
      entity_category: diagnostic
    - name: "Garage RTL433 Candidate 8"
      entity_category: diagnostic
    - name: "Garage RTL433 Candidate 9"
      entity_category: diagnostic
    - name: "Garage RTL433 Candidate 10"
      entity_category: diagnostic

switch:
  - platform: template
    name: "Garage RTL433 Discovery Mode"
    id: rtl433_discovery_mode
    optimistic: true
    restore_mode: RESTORE_DEFAULT_OFF
    entity_category: config
    turn_on_action:
      - lambda: id(rtl433_gateway).set_discovery_enabled(true);
    turn_off_action:
      - lambda: id(rtl433_gateway).set_discovery_enabled(false);

button:
  - platform: template
    name: "Garage RTL433 Clear Candidates"
    entity_category: config
    on_press:
      - rtl433_native.clear_candidates: rtl433_gateway
  - platform: template
    name: "Garage RTL433 Radio Status"
    entity_category: diagnostic
    on_press:
      - rtl433_native.status: rtl433_gateway

text:
  - platform: template
    name: "Garage Combo Fridge Mapping"
    id: garage_combo_fridge_mapping
    optimistic: true
    restore_value: true
    initial_value: "LaCrosse-TX141THBv2/0/203"
    min_length: 3
    max_length: 80
    entity_category: config
    set_action:
      - lambda: id(rtl433_gateway).set_override("garage_combo_fridge", x);
  - platform: template
    name: "Garage Combo Freezer Mapping"
    id: garage_combo_freezer_mapping
    optimistic: true
    restore_value: true
    initial_value: "TFA-303221/2/88"
    min_length: 3
    max_length: 80
    entity_category: config
    set_action:
      - lambda: id(rtl433_gateway).set_override("garage_combo_freezer", x);
  - platform: template
    name: "Garage Freezer 1 Mapping"
    id: garage_freezer_1_mapping
    optimistic: true
    restore_value: true
    initial_value: "Acurite-986/1R/11932"
    min_length: 3
    max_length: 80
    entity_category: config
    set_action:
      - lambda: id(rtl433_gateway).set_override("garage_freezer_1", x);
  - platform: template
    name: "Garage Freezer 2 Mapping"
    id: garage_freezer_2_mapping
    optimistic: true
    restore_value: true
    initial_value: "Acurite-986/2F/31274"
    min_length: 3
    max_length: 80
    entity_category: config
    set_action:
      - lambda: id(rtl433_gateway).set_override("garage_freezer_2", x);
```

- [ ] **Step 2: Apply restored text mappings during boot**

Add this block to `garage-rtl433.yaml` under `esphome:`:

```yaml
  on_boot:
    priority: -100
    then:
      - lambda: |-
          id(rtl433_gateway).set_override("garage_combo_fridge", id(garage_combo_fridge_mapping).state);
          id(rtl433_gateway).set_override("garage_combo_freezer", id(garage_combo_freezer_mapping).state);
          id(rtl433_gateway).set_override("garage_freezer_1", id(garage_freezer_1_mapping).state);
          id(rtl433_gateway).set_override("garage_freezer_2", id(garage_freezer_2_mapping).state);
```

- [ ] **Step 3: Validate ESPHome config**

Run:

```bash
./.venv/bin/python -m esphome config garage-rtl433.yaml
```

Expected: config validation succeeds and prints the resolved configuration. If `esphome` is not installed, run:

```bash
uv add --group dev esphome
./.venv/bin/python -m esphome config garage-rtl433.yaml
```

Expected: ESPHome installs into `.venv`, then config validation succeeds.

- [ ] **Step 4: Compile firmware**

Run:

```bash
./.venv/bin/python -m esphome compile garage-rtl433.yaml
```

Expected: firmware compiles for `heltec_wifi_kit_32_V2`.

- [ ] **Step 5: Commit**

```bash
git add garage-rtl433.yaml components/rtl433_native/__init__.py pyproject.toml uv.lock
git commit -m "feat: add garage rtl433 firmware config"
```

---

### Task 7: README And Migration Runbook

**Files:**
- Create: `README.md`
- Modify: `MEMORY.md`

- [ ] **Step 1: Write README**

Create `README.md`:

```markdown
# Garage RTL433 ESPHome Gateway

ESPHome replacement for the garage `OMG_Garage` OpenMQTTGateway receiver. The
firmware uses `rtl_433_ESP` on a Heltec WiFi LoRa 32 V2-style 433 MHz board and
publishes native Home Assistant entities for the known fridge/freezer sensors.

## Known Sensor Mappings

| Logical sensor | Mapping key | Current HA entity |
| --- | --- | --- |
| Garage Combo Fridge | `LaCrosse-TX141THBv2/0/203` | `sensor.garage_combo_fridge` |
| Garage Combo Freezer | `TFA-303221/2/88` | `sensor.garage_combo_freezer` |
| Garage Freezer 1 | `Acurite-986/1R/11932` | `sensor.garage_freezer_1` |
| Garage Freezer 2 | `Acurite-986/2F/31274` | `sensor.garage_freezer_2` |

## Build

```bash
uv venv .venv
uv sync --group dev
./.venv/bin/python -m esphome config garage-rtl433.yaml
./.venv/bin/python -m esphome compile garage-rtl433.yaml
```

## Discovery Workflow After Battery Changes

1. Turn on `Garage RTL433 Discovery Mode`.
2. Press `Garage RTL433 Clear Candidates`.
3. Insert batteries into one sensor or force it to transmit.
4. Watch `Garage RTL433 Candidate 1` through `Garage RTL433 Candidate 10`.
5. Copy the candidate key in `model/channel/id` format.
6. Paste it into the matching mapping text entity.
7. Confirm the logical temperature entity updates.
8. Turn off `Garage RTL433 Discovery Mode`.

The firmware never creates normal entities for unknown packets and never
automatically rebinds a freezer/fridge mapping.

## Initial Rollout

1. Flash as `garage-rtl433-native`, leaving `OMG_Garage` in place.
2. Compare the four native ESPHome entities with the existing MQTT/template
   entities for several update cycles.
3. Rename the native entities to the existing public entity IDs after the new
   values are stable.
4. Disable the OpenMQTTGateway smart-plug restart automations in a separate Home
   Assistant cleanup after the ESPHome device has proven reliable.
```

- [ ] **Step 2: Update project memory**

Append to `MEMORY.md`:

```markdown

## Implementation Notes

- Firmware config file is `garage-rtl433.yaml`.
- External component source lives in `components/rtl433_native/`.
- Runtime mapping overrides use ESPHome template text entities with
  `restore_value: true`.
- Unknown packet discovery is intentionally bounded to ten candidate text
  sensors and requires `Garage RTL433 Discovery Mode`.
```

- [ ] **Step 3: Run docs lint check**

Run:

```bash
./scripts/lint
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add README.md MEMORY.md
git commit -m "docs: add rtl433 gateway runbook"
```

---

### Task 8: End-To-End Validation Without Replacing Existing Entities

**Files:**
- Modify: `README.md`
- Modify: `MEMORY.md`

- [ ] **Step 1: Run full local checks**

Run:

```bash
./scripts/test
./scripts/lint
./.venv/bin/python -m esphome config garage-rtl433.yaml
./.venv/bin/python -m esphome compile garage-rtl433.yaml
```

Expected: all commands pass.

- [ ] **Step 2: Flash under temporary name**

Run one of these commands based on connection method:

```bash
./.venv/bin/python -m esphome upload garage-rtl433.yaml --device /dev/cu.usbserial-0001
```

or:

```bash
./.venv/bin/python -m esphome upload garage-rtl433.yaml
```

Expected: ESPHome uploads firmware and the node appears as `garage-rtl433-native`.

- [ ] **Step 3: Watch logs for decoder activity**

Run:

```bash
./.venv/bin/python -m esphome logs garage-rtl433.yaml
```

Expected: logs show received `rtl_433` messages and no repeated reboot loop.

- [ ] **Step 4: Compare Home Assistant states**

Use Home Assistant MCP or the HA UI to compare these old and new values:

```text
Old: sensor.garage_combo_fridge
New: sensor.garage_combo_fridge from the ESPHome device before final rename

Old: sensor.garage_combo_freezer
New: sensor.garage_combo_freezer from the ESPHome device before final rename

Old: sensor.garage_freezer_1
New: sensor.garage_freezer_1 from the ESPHome device before final rename

Old: sensor.garage_freezer_2
New: sensor.garage_freezer_2 from the ESPHome device before final rename
```

Expected: each native ESPHome value tracks the corresponding old MQTT/template value within one normal sensor update cycle.

- [ ] **Step 5: Verify discovery mode**

In HA:

1. Turn on `Garage RTL433 Discovery Mode`.
2. Press `Garage RTL433 Clear Candidates`.
3. Wait for nearby packets.
4. Confirm candidate text sensors fill with compact `model/channel/id` strings and packet details.
5. Turn off `Garage RTL433 Discovery Mode`.

Expected: candidates appear only while discovery mode is on, and normal unknown packet entities are not created.

- [ ] **Step 6: Record validation notes**

Append a concrete validation note to `MEMORY.md` using the actual values observed in
Steps 1 through 4. The committed note must include:

- ESPHome config validation result.
- ESPHome compile result.
- Flash target used, either the USB serial path or OTA hostname.
- First log timestamp where `rtl_433` packets were decoded.
- HA side-by-side comparison result with the old and new entity pairs observed.

- [ ] **Step 7: Commit**

```bash
git add README.md MEMORY.md
git commit -m "docs: record rtl433 validation"
```

---

## Self-Review

Spec coverage:

- OpenMQTTGateway replacement using ESPHome: Tasks 4 through 6.
- `rtl_433_ESP` decoding: Tasks 5 and 6.
- Four stable native entities: Tasks 4 and 6.
- Bounded discovery table: Tasks 3, 4, 5, and 6.
- Battery-change rebinding: Tasks 3, 6, and 7.
- Avoid unknown entity sprawl: Tasks 3, 5, 6, and 8.
- OTA stop behavior: Tasks 4 and 6.
- Stale diagnostics: Tasks 3, 4, 5, and 6.
- Testing and docs: Tasks 1, 2, 3, 7, and 8.

Type consistency:

- The codegen class is `esphome::rtl433_native::Gateway`.
- The pure state class is `rtl433_native::GatewayState`.
- Runtime overrides use `Gateway::set_override(logical_key, sensor_key)`.
- Candidate formatting uses `rtl433_native::format_candidate`.
- Mapping strings consistently use `model/channel/id`.
