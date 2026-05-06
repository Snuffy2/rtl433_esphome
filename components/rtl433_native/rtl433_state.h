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
