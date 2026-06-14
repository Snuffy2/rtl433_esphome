#pragma once

#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

#include "esphome/components/binary_sensor/binary_sensor.h"
#include "esphome/components/button/button.h"
#include "esphome/components/sensor/sensor.h"
#include "esphome/components/switch/switch.h"
#include "esphome/components/text/text.h"
#include "esphome/components/text_sensor/text_sensor.h"
#include "esphome/components/time/real_time_clock.h"
#ifdef USE_OTA_STATE_LISTENER
#include "esphome/components/ota/ota_backend.h"
#endif
#include "esphome/core/automation.h"
#include "esphome/core/component.h"
#include "esphome/core/preferences.h"

#include "rtl433_state.h"

#undef yield
#undef millis
#undef micros
#undef delay
#undef delayMicroseconds

#include "rtl_433_ESP.h"

namespace esphome::rtl433_native {

constexpr std::size_t MAPPING_TEXT_MAX_LENGTH = 240;

struct SavedLogicalState {
  bool has_value{false};
  float temperature_f{NAN};
  float humidity{NAN};
  float battery{NAN};
  int rssi{0};
  uint32_t last_updated{0};
};

struct SavedMappingText {
  bool has_value{false};
  char value[MAPPING_TEXT_MAX_LENGTH + 1]{};
};

struct SavedLogicalMapping {
  bool has_value{false};
  uint32_t fingerprint{0};
};

struct EntitySet {
  sensor::Sensor *temperature{nullptr};
  sensor::Sensor *humidity{nullptr};
  binary_sensor::BinarySensor *battery{nullptr};
  sensor::Sensor *rssi{nullptr};
  binary_sensor::BinarySensor *stale{nullptr};
  sensor::Sensor *last_updated{nullptr};
  bool stale_initialized{false};
  bool last_stale{false};
};

class MappingText;

class Gateway : public Component
#ifdef USE_OTA_STATE_LISTENER
              , public ota::OTAGlobalStateListener
#endif
{
 public:
  Gateway();

  void setup() override;
  void loop() override;
  void dump_config() override;
#ifdef USE_OTA_STATE_LISTENER
  void on_ota_global_state(ota::OTAState state, float progress, uint8_t error,
                           ota::OTAComponent *component) override;
#endif

  void stop();
  void status();
  void clear_candidates();
  void set_discovery_enabled(bool enabled);
  void set_led_pin(uint8_t led_pin) { this->led_pin_ = led_pin; }
  void set_version(const std::string &version) { this->version_ = version; }
  void add_mapping(const std::string &logical_key, const std::string &mapping);
  void set_override(const std::string &logical_key, const std::string &sensor_key);
  void set_candidate_limit(std::size_t limit);
  void set_stale_after_ms(uint32_t stale_after_ms);
  void set_temperature_sensor(const std::string &logical_key, sensor::Sensor *sensor);
  void set_humidity_sensor(const std::string &logical_key, sensor::Sensor *sensor);
  void set_battery_sensor(const std::string &logical_key, binary_sensor::BinarySensor *sensor);
  void set_rssi_sensor(const std::string &logical_key, sensor::Sensor *sensor);
  void set_stale_sensor(const std::string &logical_key, binary_sensor::BinarySensor *sensor);
  void set_last_updated_sensor(const std::string &logical_key, sensor::Sensor *sensor);
  void set_candidate_text_sensor(std::size_t index, text_sensor::TextSensor *sensor);
  void set_last_packet_sensor(text_sensor::TextSensor *sensor);
  void set_packet_count_sensor(sensor::Sensor *sensor);
  void set_known_packet_count_sensor(sensor::Sensor *sensor);
  void set_unknown_packet_count_sensor(sensor::Sensor *sensor);
  void set_discovery_enabled_sensor(binary_sensor::BinarySensor *sensor);
  void set_time(esphome::time::RealTimeClock *time) { this->time_ = time; }

 protected:
  rtl_433_ESP rf_{};
  char buffer_[512]{};
  esphome::rtl433_native::GatewayState state_{};
  std::unordered_map<std::string, EntitySet> entities_{};
  std::vector<std::string> logical_keys_{};
  std::unordered_map<std::string, ESPPreferenceObject> preferences_{};
  std::unordered_set<std::string> pending_clock_age_restore_{};
  std::unordered_map<std::string, uint32_t> last_updated_values_{};
  std::unordered_map<std::string, uint32_t> last_saved_mapping_values_{};
  std::unordered_map<std::string, uint32_t> last_state_save_ms_{};
  std::array<text_sensor::TextSensor *, 20> candidate_sensors_{};
  std::array<std::string, 20> last_candidate_values_{};
  std::string version_{"unknown"};
  text_sensor::TextSensor *last_packet_sensor_{nullptr};
  sensor::Sensor *packet_count_sensor_{nullptr};
  sensor::Sensor *known_packet_count_sensor_{nullptr};
  sensor::Sensor *unknown_packet_count_sensor_{nullptr};
  binary_sensor::BinarySensor *discovery_enabled_sensor_{nullptr};
  esphome::time::RealTimeClock *time_{nullptr};
  uint32_t time_sync_epoch_{0};
  uint32_t time_sync_ms_{0};
  uint32_t packet_count_{0};
  uint32_t known_packet_count_{0};
  uint32_t unknown_packet_count_{0};
  uint8_t led_pin_{25};
  bool restored_states_{false};
  static Gateway *instance_;

  static void process_dispatch(char *message);
  void process_message(char *message);
  void restore_saved_states();
  void sync_time_base();
  void reproject_pending_restored_states(uint32_t current_timestamp);
  uint32_t current_timestamp();
  void update_last_updated(const std::string &logical_key, uint32_t last_updated);
  void save_state(const std::string &logical_key);
  bool load_saved_mapping(const std::string &logical_key, SavedLogicalMapping &saved_mapping);
  void save_mapping_state(const std::string &logical_key);
  void publish_stale_state(const std::string &logical_key, EntitySet &entities, uint32_t now_ms);
  void publish_state(const std::string &logical_key);
  void publish_candidates();
  void publish_stale_states();
};

class DiscoverySwitch : public switch_::Switch, public Component {
 public:
  void setup() override;

  void set_parent(Gateway *parent) { this->parent_ = parent; }

 protected:
  void write_state(bool state) override;

 private:
  Gateway *parent_{nullptr};
};

class ClearCandidatesButton : public button::Button {
 public:
  void set_parent(Gateway *parent) { this->parent_ = parent; }

 protected:
  void press_action() override;

 private:
  Gateway *parent_{nullptr};
};

class StatusButton : public button::Button {
 public:
  void set_parent(Gateway *parent) { this->parent_ = parent; }

 protected:
  void press_action() override;

 private:
  Gateway *parent_{nullptr};
};

class MappingText : public text::Text, public Component {
 public:
  void setup() override;
  void dump_config() override;

  void set_parent(Gateway *parent) { this->parent_ = parent; }
  void set_logical_key(const std::string &logical_key) { this->logical_key_ = logical_key; }
  void set_initial_value(const std::string &initial_value) { this->initial_value_ = initial_value; }

 protected:
  void control(const std::string &value) override;

 private:
  Gateway *parent_{nullptr};
  std::string logical_key_{};
  std::string initial_value_{};
  ESPPreferenceObject preference_{};

  void apply_value(const std::string &value, bool save);
};

template <typename... Ts>
class StatusAction : public Action<Ts...>, public Parented<Gateway> {
 public:
  void play(Ts... x) override {
    (void) sizeof...(x);
    this->parent_->status();
  }
};

template <typename... Ts>
class StopAction : public Action<Ts...>, public Parented<Gateway> {
 public:
  void play(Ts... x) override {
    (void) sizeof...(x);
    this->parent_->stop();
  }
};

template <typename... Ts>
class ClearCandidatesAction : public Action<Ts...>, public Parented<Gateway> {
 public:
  void play(Ts... x) override {
    (void) sizeof...(x);
    this->parent_->clear_candidates();
  }
};

}  // namespace esphome::rtl433_native
