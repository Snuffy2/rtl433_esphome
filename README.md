# rtl433_esphome

ESPHome firmware and a custom component for native Home Assistant entities from `rtl_433_ESP` packets.

Current firmware profile:

- Config: `rtl433-esphome-heltec-lora-32-v2.yaml`
- ESPHome device name: `rtl433-heltec-lora-32-v2`
- Board: Heltec WiFi LoRa 32 V2-style 433 MHz ESP32
- Component source for local builds: latest GitHub release tag by default
- Local component source for development/tests: `components/rtl433_native/`
- Firmware binaries: not published, because the checked-in YAML contains deployment-specific sensor names and mappings
- The checked-in profile uses this deployment's current device and entity names. Review or replace them before OTA if your Home Assistant instance already uses different entity IDs.

## Example Known Sensor Mappings

The checked-in YAML includes one local deployment. Replace or remove these entries for your transmitters.

| Logical sensor | Mapping | Current HA entity |
| --- | --- | --- |
| Garage Fridge | `LaCrosse-TX141THBv2/0/203;TFA-303221/1/203` | `sensor.garage_fridge_temperature` |
| Garage Freezer | `TFA-303221/2/88;LaCrosse-TX141THBv2/1/88` | `sensor.garage_freezer_temperature` |

### Mapping notes

- Use `model/channel/id` keys from discovery candidates.
- Use semicolons when one physical transmitter appears under multiple decoder keys.
- Example: `LaCrosse-TX141THBv2/0/203;TFA-303221/1/203`

### Single-sensor YAML excerpt

```yaml
esphome:
  devices:
    - id: garage_fridge_device
      name: Garage Fridge

rtl433_native:
  known_sensors:
    - key: garage_fridge
      device_id: garage_fridge_device
      mapping: "LaCrosse-TX141THBv2/0/203;TFA-303221/1/203"
      entities:
        - temperature
        - humidity
        - battery
        - rssi
        - stale
        - last_updated
        - mapping
```

### Behavior

- Entity names append the type to the device name, such as `Garage Fridge Temperature`.
- `device_id` assigns generated entities to a per-sensor ESPHome sub-device.
- Omit `device_id` to keep generated entities on the main ESPHome device.
- `name` under a known sensor overrides the linked device name.
- `mapping` adds a Home Assistant text entity for runtime mapping changes.
- Mapping text values persist across reboots and OTA updates.
- RSSI and last-updated entities are disabled by default.
- Mapping text entities stay on the main device with gateway diagnostics and controls.

### Default gateway diagnostics

- `last_packet`
- `packet_count`
- `known_packet_count`
- `unknown_packet_count`
- `discovery_enabled`

### Notes

- Gateway diagnostics are disabled by default.
- Candidate text sensors come from `candidate_limit`.
- Candidate text sensors are enabled by default but are not part of the primary sensor view.
- Add diagnostic options under `rtl433_native` only to override generated settings.

### Default gateway controls

- `discovery_mode`
- `clear_candidates_button`
- `status_button`

Add control options under `rtl433_native` only to override generated settings.

## Hardware Configuration

The Heltec LoRa 32 V2 profile uses these component defaults:

```yaml
rtl433_native:
  led_pin: 25
  radio:
    module: SX1278
    frequency: 433.92
    pins:
      dio0: 26
      dio1: 35
      dio2: 34
      rst: 14
      cs: 18
      sck: 5
      miso: 19
      mosi: 27
```

For different boards or wiring:

- Override any of those values under `rtl433_native`.
- Use substitutions if you want board-specific values at the top of the file.

```yaml
substitutions:
  led_pin: "25"
  rf_module: SX1278
  rf_frequency: "433.92"
  rf_dio0_pin: "26"
  rf_dio1_pin: "35"
  rf_dio2_pin: "34"
  rf_rst_pin: "14"
  rf_cs_pin: "18"
  rf_sck_pin: "5"
  rf_miso_pin: "19"
  rf_mosi_pin: "27"

rtl433_native:
  led_pin: ${led_pin}
  radio:
    module: ${rf_module}
    frequency: ${rf_frequency}
    pins:
      dio0: ${rf_dio0_pin}
      dio1: ${rf_dio1_pin}
      dio2: ${rf_dio2_pin}
      rst: ${rf_rst_pin}
      cs: ${rf_cs_pin}
      sck: ${rf_sck_pin}
      miso: ${rf_miso_pin}
      mosi: ${rf_mosi_pin}
```

## Build

### Default local build

```bash
uv sync --dev
./scripts/build
```

### Build behavior

- Validates the ESPHome config.
- Compiles with `PLATFORMIO_BUILD_JOBS=1`.
- Builds `rtl433-esphome-heltec-lora-32-v2.yaml` by default.
- Passes `rtl433_esphome_ref` through to ESPHome as the external component Git ref.
- Uses the moving `latest` Git tag by default.

### Build from a specific component release or Git ref

```bash
RTL433_ESPHOME_REF=v0.1.0 ./scripts/build
```

### Build another board profile

```bash
FIRMWARE_CONFIG=path/to/another-board.yaml ./scripts/build
```

### Preflight options

- `./scripts/build --preflight`: regenerate PlatformIO config and repair stale generated platform cache before compiling.
- `./scripts/esphome-preflight`: run manually before OTA upload after Python, ESPHome, or PlatformIO changes.
- `--update-global`: also refresh PlatformIO Core/global packages.

## Discovery Workflow

The names below use the default Heltec profile `friendly_name`.

1. Turn on `rtl433_esphome heltec_lora_32_v2 Discovery Mode`.
2. Press `rtl433_esphome heltec_lora_32_v2 Clear Candidates`.
3. Insert batteries into one sensor or force it to transmit.
4. Watch `rtl433_esphome heltec_lora_32_v2 Candidate 1` through `rtl433_esphome heltec_lora_32_v2 Candidate 10`.
5. Copy the candidate key in `model/channel/id` format.
6. Paste it into the matching mapping text entity. Use semicolons to list multiple keys for the same physical sensor.
7. Confirm the logical temperature entity updates.
8. Turn off `rtl433_esphome heltec_lora_32_v2 Discovery Mode`.

The firmware never creates normal entities for unknown packets and never automatically rebinds a freezer/fridge mapping.
