# rtl433_esphome

Use an ESPHome device as a local `rtl_433` receiver and expose selected temperature, humidity, battery, RSSI, stale, and last-updated entities directly in Home Assistant. You start from a checked-in ESPHome YAML file, adjust it for your board and sensors, then install it with ESPHome.

## Install

Start from the included `rtl433-esphome-heltec-lora-32-v2.yaml` file. It is the only profile in the repository today, and it targets a Heltec WiFi LoRa 32 V2-style ESP32 with an SX1278 radio at 433.92 MHz.

Firmware binaries are not published because the YAML contains deployment-specific device names, Home Assistant names, and sensor mappings. Review those values before installing it on your own device.

See [YAML Configuration](#yaml_configuration) below for details on the options.

1. Copy `rtl433-esphome-heltec-lora-32-v2.yaml` into your ESPHome project or import it into the ESPHome dashboard.
2. Update the top-level substitutions:
   - `device_name`: the ESPHome node name.
   - `friendly_name`: the display name shown in Home Assistant.
   - `rtl433_esphome_ref`: keep `latest` unless you want to pin a release tag.
3. Make sure your ESPHome secrets provide `wifi_ssid`, `wifi_password`, and `fallback_ap_password`.
4. Check the hardware settings. If you are using a different ESP32 board, radio module, frequency, or pin wiring, update the board settings and the `rtl433_native.radio` section.
5. List the physical sensors you want to track under `esphome.devices`. These are the Home Assistant sub-devices, such as `Garage Fridge` or `Garage Freezer`.
6. List the same logical sensors under `rtl433_native.known_sensors`.
   For each sensor, choose:
   - `key`: a stable YAML key, such as `garage_fridge`.
   - `device_id`: the matching ID from `esphome.devices`.
   - `mapping`: the `model/channel/id` key for the physical transmitter.
   - `entities`: the readings you want Home Assistant to create.
7. Keep the Home Assistant time source in the YAML:

   ```yaml
   time:
     - platform: homeassistant
       id: homeassistant_time

   rtl433_native:
     time_id: homeassistant_time
   ```

   The custom component requires `time_id` for restored stale-state aging and last-updated timestamps.

8. In the ESPHome dashboard, choose the device and select **Install**.
9. After the device is online in Home Assistant, use discovery mode to find each sensor's `model/channel/id` key, then paste that key into the matching mapping entity.

## Discovery Workflow

Use Discovery Mode when you need to identify which `rtl_433` packet belongs to which real-world sensor. The most common times to use it are:

- First install, when you are creating your initial `known_sensors` mappings.
- Adding another fridge, freezer, weather station, or other 433 MHz transmitter.
- Replacing batteries, if the transmitter comes back with a different ID.
- Troubleshooting a sensor that stopped updating because its mapping no longer
  matches the packets being received.

Normal operation does not require Discovery Mode. Known sensors keep updating while it is off, and unknown packets are ignored instead of becoming regular Home Assistant entities. Turning Discovery Mode on temporarily gives you a bounded candidate list so you can copy the right `model/channel/id` key into the mapping for a known sensor.

*The names below use the default Heltec profile `friendly_name`.*

1. Turn on `rtl433_esphome heltec_lora_32_v2 Discovery Mode`.
2. Press `rtl433_esphome heltec_lora_32_v2 Clear Candidates` so the list starts
   empty.
3. Make one physical sensor transmit. For battery-powered sensors, removing and
   reinserting the batteries is often the easiest way to force a packet.
4. Watch `rtl433_esphome heltec_lora_32_v2 Candidate 1` through
   `rtl433_esphome heltec_lora_32_v2 Candidate 10`.
5. Look for the candidate whose temperature, humidity, battery, and RSSI values
   match the sensor you just triggered.
6. Copy the candidate key at the start of the value. It uses
   `model/channel/id` format.
7. Paste that key into the matching mapping text entity. Use semicolons to list
   multiple keys for the same physical sensor.
8. Confirm the logical temperature or humidity entity updates.
9. Repeat the clear-and-trigger process for each additional sensor.
10. Turn off `rtl433_esphome heltec_lora_32_v2 Discovery Mode`.

Work through one sensor at a time when possible. Many 433 MHz devices transmit on their own schedule, so clearing the candidate list before each sensor makes it easier to tell which packet belongs to the sensor in your hand.

## YAML Configuration

### Configure Sensors

The checked-in YAML includes one local deployment as an example. Replace or remove these entries for your transmitters.

#### Choosing a Mapping

- Use `model/channel/id` keys from discovery candidates.
- Use semicolons when one physical transmitter appears under multiple decoder keys.
- Example: `LaCrosse-TX141THBv2/0/203;TFA-303221/1/203`

#### Single-Sensor Example

```yaml
esphome:
  devices:
    - id: garage_fridge_device
      name: Garage Fridge

time:
  - platform: homeassistant
    id: homeassistant_time

rtl433_native:
  time_id: homeassistant_time
  known_sensors:
    - key: garage_fridge
      device_id: garage_fridge_device
      entities:
        - humidity
        - battery
        - rssi
        - stale
        - last_updated
        - mapping
```

#### Entity Behavior

- Generated known-sensor entity names are data-point names only, such as `Temperature`. Home Assistant combines them with the linked device name for display and entity IDs.
- `device_id` assigns generated entities to a per-sensor ESPHome sub-device.
- Use `device_id` when configuring more than one known sensor; without it, generated entities stay on the main ESPHome device and duplicate data-point names are rejected.
- `mapping` is optional. Omit it when the `model/channel/id` key is not known yet.
- Adding `mapping` to `entities` creates a gateway-local Home Assistant text entity named from the known sensor, such as `Garage Fridge Mapping`.
- If the top-level `mapping` value is omitted, the sensor must list `mapping` under `entities` so the discovered key can be entered later.
- Mapping text entities can start blank; use Discovery Mode to find a key and paste it into the text entity.
- `temperature` is optional. List only the entity types you want, such as `humidity` and `mapping` for a humidity-only sensor.
- Mapping text values persist across reboots and OTA updates.
- RSSI and last-updated entities are disabled by default.
- Mapping text entities stay on the main ESPHome device even when `device_id` is set.
- `time_id` is required so restored stale-state aging and last-updated timestamps use a real wall-clock source.

#### Available Known-Sensor Entities

Add only the entities you want for each known sensor:

- temperature
- humidity
- battery
- rssi
- stale
- last_updated
- mapping

`mapping` creates the Home Assistant text entity used to change the transmitter key without editing YAML after the device is installed.

### Gateway Diagnostics and Controls

#### Default Gateway Diagnostics

- last_packet
- packet_count
- known_packet_count
- unknown_packet_count

#### Notes

- Gateway diagnostics are disabled by default.
- Candidate text sensors come from `candidate_limit`.
- Candidate text sensors are enabled by default but are not part of the primary sensor view.
- Add diagnostic options under `rtl433_native` only to override generated settings.

#### Default Gateway Controls

- discovery_mode
- clear_candidates_button
- status_button

Add control options under `rtl433_native` only to override generated settings.

### Hardware Configuration Reference

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
<details>
<summary><h2>Local Build</h2></summary>

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

</details>
