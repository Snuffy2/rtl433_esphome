#pragma once

#include <cmath>
#include <cstdint>
#include <optional>
#include <string>
#include <unordered_map>
#include <vector>

namespace esphome::rtl433_native {

struct SensorKey {
  std::string model;
  std::string channel;
  std::string id;
};

struct SensorMapping {
  SensorKey primary;
  std::vector<SensorKey> synonyms{};
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

enum class PacketResult {
  MATCHED_KNOWN,
  RECORDED_CANDIDATE,
  IGNORED_UNKNOWN,
  REJECTED_INVALID,
};

std::optional<SensorKey> parse_sensor_key(const std::string &value);
std::optional<SensorMapping> parse_sensor_mapping(const std::string &value);
std::string format_sensor_key(const SensorKey &key);
std::string format_sensor_mapping(const SensorMapping &mapping);
uint32_t sensor_mapping_hash(const std::string &mapping_value);
std::string format_candidate(const CandidateRow &candidate);
bool matches_key(const DecodedPacket &packet, const SensorKey &key);
uint32_t resolve_last_updated_timestamp(uint32_t current_timestamp, uint32_t previous_timestamp);
uint32_t resolve_projected_timestamp(uint32_t sync_epoch, uint32_t sync_ms, uint32_t now_ms);
uint32_t resolve_restored_last_seen_ms(
    uint32_t saved_last_updated, uint32_t current_timestamp, uint32_t now_ms, uint32_t stale_after_ms);
uint32_t unchanged_state_save_interval_ms(uint32_t stale_after_ms);
bool should_persist_logical_state(
    bool value_changed, uint32_t now_ms, uint32_t previous_save_ms, uint32_t interval_ms);

class GatewayState {
 public:
  bool set_mapping(const std::string &logical_key, const std::string &mapping);
  void restore_logical_state(const std::string &logical_key, const LogicalSensorState &state);
  const LogicalSensorState *logical_sensor(const std::string &logical_key) const;
  std::optional<uint32_t> mapping_hash(const std::string &logical_key) const;
  PacketResult process_packet(const DecodedPacket &packet);
  const std::vector<std::string> &matched_logical_keys() const { return matched_logical_keys_; }
  const std::vector<std::string> &changed_logical_keys() const { return changed_logical_keys_; }
  void set_discovery_enabled(bool enabled) { discovery_enabled_ = enabled; }
  bool discovery_enabled() const { return discovery_enabled_; }
  void set_candidate_limit(std::size_t limit) { candidate_limit_ = limit; }
  std::size_t candidate_limit() const { return candidate_limit_; }
  void set_stale_after_ms(uint32_t stale_after_ms) { stale_after_ms_ = stale_after_ms; }
  uint32_t stale_after_ms() const { return stale_after_ms_; }
  void clear_candidates() { candidates_.clear(); }
  const std::vector<CandidateRow> &candidates() const { return candidates_; }
  std::optional<uint32_t> next_stale_state_publish_delay_ms(uint32_t now_ms) const;
  bool is_stale(const std::string &logical_key, uint32_t now_ms) const;

 private:
  std::unordered_map<std::string, SensorMapping> mappings_{};
  std::unordered_map<std::string, uint32_t> mapping_hashes_{};
  std::unordered_map<std::string, LogicalSensorState> logical_states_{};
  std::vector<std::string> matched_logical_keys_{};
  std::vector<std::string> changed_logical_keys_{};
  bool discovery_enabled_{false};
  std::size_t candidate_limit_{10};
  uint32_t stale_after_ms_{3600000};
  std::vector<CandidateRow> candidates_{};
  void record_candidate(const DecodedPacket &packet, bool matched_known);
  void prune_candidates(uint32_t now_ms);
};

}  // namespace esphome::rtl433_native
