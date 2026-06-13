# rtl433_esphome

ESPHome firmware and a local custom component for building native Home
Assistant entities from `rtl_433_ESP` packets.

The current checked-in firmware profile targets a Heltec WiFi LoRa 32 V2-style
433 MHz ESP32 board:

- Config: `rtl433-esphome-heltec-lora-32-v2.yaml`
- ESPHome device name: `rtl433-heltec-lora-32-v2`
- Release build name: `rtl433_esphome-heltec_lora_32_v2`

Future profiles can add more board-specific YAML files while reusing the same
`components/rtl433_native/` component and build scripts.

## Example Known Sensor Mappings

The default YAML includes four garage freezer/fridge sensors as an example
deployment. Replace or remove these entries for your own transmitters.

| Logical sensor | Mapping | Current HA entity |
| --- | --- | --- |
| Garage Combo Fridge | `LaCrosse-TX141THBv2/0/203;TFA-303221/1/203` | `sensor.garage_combo_fridge` |
| Garage Combo Freezer | `TFA-303221/2/88;LaCrosse-TX141THBv2/1/88` | `sensor.garage_combo_freezer` |
| Garage Freezer 1 | `Acurite-986/1R/11932` | `sensor.garage_freezer_1` |
| Garage Freezer 2 | `Acurite-986/2F/31274` | `sensor.garage_freezer_2` |

Use semicolon-delimited mappings when rtl_433 reports the same physical
transmitter under more than one decoder key. Each entry uses the
`model/channel/id` format shown in discovery candidates.

Known sensors can use the compact form:

```yaml
esphome:
  devices:
    - id: garage_combo_fridge_device
      name: Garage Combo Fridge

rtl433_native:
  known_sensors:
    - key: garage_combo_fridge
      device_id: garage_combo_fridge_device
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

Compact entries generate entity names by appending the entity type to the linked
device name, such as `Garage Combo Fridge Temperature`, `Garage Combo Fridge
Humidity`, `Garage Combo Fridge RSSI`, and `Garage Combo Fridge Last Updated`.
Set `device_id` on each compact known sensor to assign its generated entities
to a per-sensor ESPHome sub-device, such as `Garage Combo Fridge` or `Garage
Freezer 1`. If `name` is also set under a known sensor, that value overrides the
linked device name for generated entity names. If `device_id` is omitted, the
generated known-sensor entities stay on the main ESPHome device. The `mapping`
entity is optional; include it when you want a Home Assistant text entity for
changing the rtl_433 mapping at runtime. Mapping text entities stay on the main
ESPHome device with gateway diagnostics, discovery
candidates, controls, uptime, status, restart, IP address, Wi-Fi RSSI, and free
heap. Compact RSSI and last-updated entities are disabled by default.

Mapping text entity values are saved on the device. After a mapping is changed
from Home Assistant, the saved value continues to override the YAML default
across reboots and OTA updates until the mapping text entity is changed again.

Use the verbose form instead when an entity needs custom options:

```yaml
esphome:
  devices:
    - id: garage_combo_fridge_device
      name: Garage Combo Fridge

rtl433_native:
  known_sensors:
    - key: garage_combo_fridge
      device_id: garage_combo_fridge_device
      mapping: "LaCrosse-TX141THBv2/0/203;TFA-303221/1/203"
      temperature:
        name: "Garage Combo Fridge Temperature"
      humidity:
        name: "Garage Combo Fridge Humidity"
```

Gateway diagnostics are created by default and do not need to be listed in
the board profile YAML:

- `last_packet`
- `packet_count`
- `known_packet_count`
- `unknown_packet_count`
- `discovery_enabled`

Add any of those options under `rtl433_native` only when overriding the generated
name or other entity settings. These gateway diagnostics are disabled by
default.

Candidate text sensors are created from `candidate_limit` as diagnostic entities
and are enabled by default, but they are not part of the primary sensor view.

Gateway controls are also created by default and do not need template `switch`
or `button` entries in the board profile YAML:

- `discovery_mode`
- `clear_candidates_button`
- `status_button`

Add any of those options under `rtl433_native` only when overriding the generated
name or other entity settings.

## Hardware Configuration

`rtl433-esphome-heltec-lora-32-v2.yaml` uses the `rtl433_native`
component-supplied hardware defaults for the Heltec LoRa 32 V2 profile:

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

Users with different boards or wiring can still add any of those options back
under `rtl433_native`. They can also keep the values as YAML substitutions if
they prefer a board profile at the top of the file:

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

```bash
uv sync --dev
./scripts/build
```

`./scripts/build` validates the ESPHome config and compiles with
`PLATFORMIO_BUILD_JOBS=1`. By default it builds
`rtl433-esphome-heltec-lora-32-v2.yaml`. Override `FIRMWARE_CONFIG` to build a
future board profile:

```bash
FIRMWARE_CONFIG=path/to/another-board.yaml ./scripts/build
```

Use `./scripts/build --preflight` when the generated PlatformIO platform cache
may need repair before compiling.

Run `./scripts/esphome-preflight` before OTA upload when the PlatformIO cache
may be stale, after changing Python versions, or after ESPHome updates. It
finds ESPHome's generated `platformio.ini` and force-reinstalls the URL-pinned
ESP32 platform selected by ESPHome. Add `--update-global` to also refresh
PlatformIO Core/global packages when you intentionally want the network-backed
global update step.

## Discovery Workflow

The entity names below use the default Heltec profile friendly name. If you
change `friendly_name`, Home Assistant will use that name instead.

1. Turn on `rtl433_esphome heltec_lora_32_v2 Discovery Mode`.
2. Press `rtl433_esphome heltec_lora_32_v2 Clear Candidates`.
3. Insert batteries into one sensor or force it to transmit.
4. Watch `rtl433_esphome heltec_lora_32_v2 Candidate 1` through
   `rtl433_esphome heltec_lora_32_v2 Candidate 10`.
5. Copy the candidate key in `model/channel/id` format.
6. Paste it into the matching mapping text entity. Use semicolons to list
   multiple keys for the same physical sensor.
7. Confirm the logical temperature entity updates.
8. Turn off `rtl433_esphome heltec_lora_32_v2 Discovery Mode`.

The firmware never creates normal entities for unknown packets and never
automatically rebinds a freezer/fridge mapping.
