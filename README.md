# Garage RTL433 ESPHome Gateway

ESPHome replacement for an OpenMQTTGateway receiver. The firmware uses `rtl_433_ESP` on a Heltec WiFi LoRa 32 V2-style 433 MHz board and publishes native Home Assistant entities for the known sensors.

## Known Sensor Mappings

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
rtl433_native:
  known_sensors:
    - key: garage_combo_fridge
      name: "Garage Combo Fridge"
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

Compact entries generate entity names by appending the entity type, such as
`Garage Combo Fridge Temperature`, `Garage Combo Fridge Humidity`, `Garage
Combo Fridge RSSI`, and `Garage Combo Fridge Last Updated`. The `mapping`
entity is optional; include it when you want a Home Assistant text entity for
changing the rtl_433 mapping at runtime.

Use the verbose form instead when an entity needs custom options:

```yaml
rtl433_native:
  known_sensors:
    - key: garage_combo_fridge
      name: "Garage Combo Fridge"
      mapping: "LaCrosse-TX141THBv2/0/203;TFA-303221/1/203"
      temperature:
        name: "Garage Combo Fridge Temperature"
      humidity:
        name: "Garage Combo Fridge Humidity"
        entity_category: diagnostic
```

Gateway diagnostics are created by default and do not need to be listed in
`garage-rtl433.yaml`:

- `last_packet`
- `packet_count`
- `known_packet_count`
- `unknown_packet_count`
- `discovery_enabled`

Add any of those options under `rtl433_native` only when overriding the generated
name or other entity settings.

Gateway controls are also created by default and do not need template `switch`
or `button` entries in `garage-rtl433.yaml`:

- `discovery_mode`
- `clear_candidates_button`
- `status_button`

Add any of those options under `rtl433_native` only when overriding the generated
name or other entity settings.

## Hardware Configuration

`garage-rtl433.yaml` uses the `rtl433_native` component-supplied hardware
defaults:

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
uv venv .venv
uv sync --group dev
./.venv/bin/python -m esphome config garage-rtl433.yaml
./.venv/bin/python -m esphome compile garage-rtl433.yaml
```

## Discovery Workflow

1. Turn on `Garage RTL433 Discovery Mode`.
2. Press `Garage RTL433 Clear Candidates`.
3. Insert batteries into one sensor or force it to transmit.
4. Watch `Garage RTL433 Candidate 1` through `Garage RTL433 Candidate 10`.
5. Copy the candidate key in `model/channel/id` format.
6. Paste it into the matching mapping text entity. Use semicolons to list
   multiple keys for the same physical sensor.
7. Confirm the logical temperature entity updates.
8. Turn off `Garage RTL433 Discovery Mode`.

The firmware never creates normal entities for unknown packets and never
automatically rebinds a freezer/fridge mapping.
