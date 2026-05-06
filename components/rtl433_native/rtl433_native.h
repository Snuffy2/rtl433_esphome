#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <string>
#include <unordered_map>

#include "esphome/components/binary_sensor/binary_sensor.h"
#include "esphome/components/sensor/sensor.h"
#include "esphome/components/text_sensor/text_sensor.h"
#include "esphome/core/automation.h"
#include "esphome/core/component.h"

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
  bool stale_initialized{false};
  bool last_stale{false};
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
  void add_mapping(const std::string &logical_key, const std::string &model, const std::string &channel,
                  const std::string &id);
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
  void set_known_packet_count_sensor(sensor::Sensor *sensor);
  void set_unknown_packet_count_sensor(sensor::Sensor *sensor);
  void set_discovery_enabled_sensor(binary_sensor::BinarySensor *sensor);

 protected:
  rtl_433_ESP rf_{};
  char buffer_[512]{};
  esphome::rtl433_native::GatewayState state_{};
  std::unordered_map<std::string, EntitySet> entities_{};
  std::array<text_sensor::TextSensor *, 20> candidate_sensors_{};
  std::array<std::string, 20> last_candidate_values_{};
  text_sensor::TextSensor *last_packet_sensor_{nullptr};
  sensor::Sensor *packet_count_sensor_{nullptr};
  sensor::Sensor *known_packet_count_sensor_{nullptr};
  sensor::Sensor *unknown_packet_count_sensor_{nullptr};
  binary_sensor::BinarySensor *discovery_enabled_sensor_{nullptr};
  uint32_t packet_count_{0};
  uint32_t known_packet_count_{0};
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
