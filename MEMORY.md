# Project Memory

## 2026-05-06

- Project started as an ESPHome replacement for the garage `OMG_Garage`
  OpenMQTTGateway device.
- Home Assistant reported `OMG_Garage` as MQTT manufacturer `OMG_community`,
  firmware `v1.8.1`, model flags `["HELTEC_SSD1306","WebUI","rtl_433"]`,
  area `garage`, identifier `7C9EBD5ACFF8`.
- Current logical freezer/fridge mappings discovered from HA:
  - Garage Combo - Fridge: `LaCrosse-TX141THBv2-0-203`,
    `sensor.garage_combo_fridge`.
  - Garage Combo - Freezer: `TFA-303221-2-88`,
    `sensor.garage_combo_freezer`.
  - Garage Freezer 1: `Acurite-986-1R-11932`,
    `sensor.garage_freezer_1`.
  - Garage Freezer 2: `Acurite-986-2F-31274`,
    `sensor.garage_freezer_2`.
- Design direction approved: hybrid ESPHome native entities using
  `rtl_433_ESP`, with strict known-sensor mappings plus a bounded candidate
  table for discovering replacement IDs after battery changes.
- Host-side validation and static checks are complete, but the requested Task 8
  live flash/HA comparison remains pending until a hardware rollout is performed.
- Implementation plan written at
  `docs/superpowers/plans/2026-05-06-rtl433-esphome-hybrid.md`.

## Implementation Notes

- Firmware config file is `garage-rtl433.yaml`.
- External component source lives in `components/rtl433_native/`.
- Runtime mapping overrides use ESPHome template text entities with
  `restore_value: true`.
- Unknown packet discovery is intentionally bounded to ten candidate text
  sensors and requires `Garage RTL433 Discovery Mode`.

## 2026-06-08

- Flashed `garage-rtl433-native` to the locally connected ESP32 at
  `/dev/cu.usbserial-0001`; esptool identified the device as ESP32-D0WDQ6,
  MAC `7c:9e:bd:5a:cf:f8`.
- PlatformIO could not build from the project path because `AI Projects`
  contains a space, so the flash build used a temporary copy at
  `/private/tmp/rtl433_esphome_flash`.
- The first flashed image boot-looped because the SX1278 was initialized on
  default SPI pins. Added Heltec LoRa SPI build flags:
  `RF_MODULE_SCK=5`, `RF_MODULE_MISO=19`, and `RF_MODULE_MOSI=27`.
- Rebuilt with `PLATFORMIO_BUILD_JOBS=1` to avoid compiler `Error -11`
  crashes, flashed the corrected factory image, and verified over serial that
  the radio watchdog loop was gone.
- After updating ignored `secrets.yaml`, rebuilt and reflashed the factory
  image. Serial logs showed Wi-Fi connected with IP `10.100.50.130`, and
  `rtl433_native` received known LaCrosse packets.
- Added the working config to Home Assistant's ESPHome Builder directory at
  `/home/pi/homeassistant/esphome/garage-rtl433.yaml`, copied ignored
  `secrets.yaml`, and installed the local custom component under
  `/home/pi/homeassistant/esphome/components/rtl433_native/`.
- Validation inside the HA ESPHome Builder container
  `addon_5c53de3b_esphome` passed with
  `esphome config /config/esphome/garage-rtl433.yaml`.
- Disabled the visible onboard activity LED by removing the
  `ONBOARD_LED=25` build flag. `rtl_433_ESP` only initializes and toggles the
  LED when `ONBOARD_LED` is defined.
- Recompiled with `PLATFORMIO_BUILD_JOBS=1`, updated the Home Assistant
  ESPHome Builder copy, and OTA uploaded the new firmware to `10.100.50.130`.
  Post-OTA logs showed the device connected and decoded a known
  `Acurite-986/2F/31274` packet.
- The LED stopped flashing but stayed solid white, so `garage-rtl433.yaml`
  now explicitly drives GPIO25 low in `on_boot`. Recompiled, updated the HA
  ESPHome Builder copy, and OTA uploaded successfully; post-OTA logs showed
  Wi-Fi/API connected at `10.100.50.130`.
- Fixed known-sensor temperature updates by parsing `temperature_C` and
  `temperature_1_C` and converting to Fahrenheit before publishing. Changed
  known-sensor `battery` entries from numeric battery sensors to binary battery
  sensors; `battery_ok=1` publishes `OFF` because Home Assistant binary
  battery device class treats `ON` as low battery. Recompiled, updated the HA
  ESPHome Builder component copy, and OTA uploaded successfully. Logs verified
  `Acurite-986/1R/11932` published `Garage Freezer 1` at `74.00 °F` and
  `Garage Freezer 1 Battery` as `OFF`.
- Pulled the user-edited ESPHome Builder YAML back into the repo before adding
  persistence. Known-sensor temperature, humidity, battery, RSSI, and
  last-updated timestamp values are saved to ESPHome preferences and restored
  after device restarts. The three packet counters now publish `0` during
  component setup so HA does not show `unknown` on boot before the first
  packet.
- Last-updated entities are ESPHome sensor entities with
  `device_class: timestamp`, not text sensors. HA initially assigned `_2`
  suffixes because of prior text-sensor registry history; the live timestamp
  entities were renamed through the HA entity-registry API to the intended
  base IDs. Recompiled locally with `PLATFORMIO_BUILD_JOBS=1`, validated inside
  the ESPHome Builder container, OTA uploaded to `10.100.50.130`, and verified
  HA states such as
  `sensor.garage_rtl433_garage_combo_fridge_last_updated` report timestamp
  device class with ISO timestamp state.
- The ESP32/framework time source did not reliably advance for custom
  last-updated publishing, so the final firmware keeps a per-sensor monotonic
  fallback: use the HA time component when it moves forward, otherwise advance
  the persisted timestamp by at least one second per accepted known packet.
  Final OTA build was compiled locally with ESPHome 2026.4.5 at 2026-06-08
  17:59:58 -0400 and uploaded to `10.100.50.130`; logs verified Fahrenheit
  temperatures and advancing timestamp values such as `1780956032` then
  `1780956160`.
- ESPHome Builder 2026.5.3 validates the final YAML/component source, but a
  forced clean Builder compile failed before reaching project code because its
  PlatformIO dependency graph did not add Arduino `Network.h` /
  `NetworkInterface.h` include paths for `AsyncTCP`. Local ESPHome 2026.4.5 is
  currently the reliable compile/upload path for this device.
- Fixed immediate stale-on-after-reboot for restored logical sensors. Root
  cause: `on_boot` reapplied template text mapping overrides, and
  `GatewayState::set_mapping()` cleared the restored logical state even when
  the mapping key was unchanged. Same-key mapping updates now preserve restored
  values; actual remaps and invalid mappings still clear state. OTA build
  compiled locally at 2026-06-08 20:06:00 -0400 and uploaded to
  `10.100.50.130`; HA verified
  `binary_sensor.garage_rtl433_native_garage_freezer_2_stale` returned `off`
  immediately after reboot while its restored last-updated timestamp remained
  `2026-06-08T23:49:20+00:00`.
