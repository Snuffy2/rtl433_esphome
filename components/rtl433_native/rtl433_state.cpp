#include "rtl433_state.h"

#include <algorithm>
#include <cmath>
#include <sstream>
#include <utility>

#if __has_include("esphome/core/log.h")
#include "esphome/core/log.h"
#else
#define ESP_LOGW(tag, ...) ((void) (tag))
#endif

namespace esphome::rtl433_native {

namespace {

static const char *const TAG = "rtl433_state";
constexpr uint32_t DEFAULT_UNCHANGED_STATE_SAVE_INTERVAL_MS = 60000;
constexpr uint32_t LAST_UPDATED_PAST_BIAS_SECONDS = 60;

bool same_key(const SensorKey &left, const SensorKey &right) {
  return left.model == right.model && left.channel == right.channel && left.id == right.id;
}

bool key_less(const SensorKey &left, const SensorKey &right) {
  if (left.model != right.model) {
    return left.model < right.model;
  }
  if (left.channel != right.channel) {
    return left.channel < right.channel;
  }
  return left.id < right.id;
}

std::string trim_ascii_whitespace(const std::string &value) {
  const auto first = value.find_first_not_of(" \t\n\r\f\v");
  if (first == std::string::npos) {
    return "";
  }
  const auto last = value.find_last_not_of(" \t\n\r\f\v");
  return value.substr(first, last - first + 1);
}

void canonicalize_mapping(SensorMapping &mapping) {
  std::vector<SensorKey> keys{mapping.primary};
  keys.insert(keys.end(), mapping.synonyms.begin(), mapping.synonyms.end());
  std::sort(keys.begin(), keys.end(), key_less);
  keys.erase(std::unique(keys.begin(), keys.end(), same_key), keys.end());
  mapping.primary = keys.front();
  mapping.synonyms.assign(std::next(keys.begin()), keys.end());
}

bool same_mapping(const SensorMapping &left, const SensorMapping &right) {
  if (!same_key(left.primary, right.primary) || left.synonyms.size() != right.synonyms.size()) {
    return false;
  }
  for (std::size_t index = 0; index < left.synonyms.size(); ++index) {
    if (!same_key(left.synonyms[index], right.synonyms[index])) {
      return false;
    }
  }
  return true;
}

CandidateRow make_candidate_row(const DecodedPacket &packet, bool matched_known) {
  CandidateRow row;
  row.key = SensorKey{packet.model, packet.channel, packet.id};
  row.temperature_f = packet.temperature_f;
  row.humidity = packet.humidity;
  row.battery = packet.battery;
  row.rssi = packet.rssi;
  row.first_seen_ms = packet.seen_ms;
  row.last_seen_ms = packet.seen_ms;
  row.packet_count = 1;
  row.matched_known = matched_known;
  return row;
}

bool candidate_less(const CandidateRow &left, const CandidateRow &right) {
  if (left.last_seen_ms != right.last_seen_ms) {
    return left.last_seen_ms > right.last_seen_ms;
  }
  return key_less(left.key, right.key);
}

bool is_older_than(uint32_t now_ms, uint32_t seen_ms, uint32_t age_ms) {
  return static_cast<uint32_t>(now_ms - seen_ms) > age_ms;
}

bool same_float_value(float left, float right) {
  return left == right || (std::isnan(left) && std::isnan(right));
}

bool same_persisted_values(const LogicalSensorState &state, const DecodedPacket &packet) {
  return same_float_value(state.temperature_f, packet.temperature_f) &&
         same_float_value(state.humidity, packet.humidity) &&
         same_float_value(state.battery, packet.battery);
}

}  // namespace

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
  model = trim_ascii_whitespace(model);
  channel = trim_ascii_whitespace(channel);
  id = trim_ascii_whitespace(id);
  if (model.empty() || channel.empty() || id.empty()) {
    return std::nullopt;
  }
  return SensorKey{model, channel, id};
}

std::optional<SensorMapping> parse_sensor_mapping(const std::string &value) {
  std::stringstream stream(value);
  std::string segment;
  SensorMapping mapping;
  bool has_primary = false;

  while (std::getline(stream, segment, ';')) {
    auto trimmed_segment = trim_ascii_whitespace(segment);
    auto parsed = parse_sensor_key(trimmed_segment);
    if (!parsed.has_value()) {
      ESP_LOGW(TAG, "parse_sensor_mapping rejected invalid segment '%s' in '%s'", segment.c_str(), value.c_str());
      return std::nullopt;
    }
    if (!has_primary) {
      mapping.primary = *parsed;
      has_primary = true;
      continue;
    }
    if (same_key(mapping.primary, *parsed)) {
      continue;
    }
    if (std::any_of(mapping.synonyms.begin(), mapping.synonyms.end(), [&](const SensorKey &synonym) {
          return same_key(synonym, *parsed);
        })) {
      continue;
    }
    mapping.synonyms.push_back(*parsed);
  }

  if (!has_primary || (!value.empty() && value.back() == ';')) {
    ESP_LOGW(TAG, "parse_sensor_mapping rejected invalid mapping '%s'", value.c_str());
    return std::nullopt;
  }
  canonicalize_mapping(mapping);
  return mapping;
}

std::string format_sensor_key(const SensorKey &key) {
  return key.model + "/" + key.channel + "/" + key.id;
}

std::string format_sensor_mapping(const SensorMapping &mapping) {
  std::string value = format_sensor_key(mapping.primary);
  for (const auto &synonym : mapping.synonyms) {
    value += ";" + format_sensor_key(synonym);
  }
  return value;
}

uint32_t sensor_mapping_hash(const std::string &mapping_value) {
  uint32_t hash = 2166136261UL;
  for (char value : mapping_value) {
    hash ^= static_cast<uint8_t>(value);
    hash *= 16777619UL;
  }
  return hash == 0 ? 2166136261UL : hash;
}

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

bool matches_key(const DecodedPacket &packet, const SensorKey &key) {
  return packet.model == key.model && packet.channel == key.channel && packet.id == key.id;
}

uint32_t resolve_last_updated_timestamp(uint32_t current_timestamp, uint32_t previous_timestamp) {
  if (current_timestamp > 0) {
    // Bias the published timestamp into the past so Home Assistant relative-time
    // displays stay on the "ago" side even if the device clock is slightly ahead.
    if (current_timestamp > LAST_UPDATED_PAST_BIAS_SECONDS) {
      return current_timestamp - LAST_UPDATED_PAST_BIAS_SECONDS;
    }
    return current_timestamp;
  }
  return previous_timestamp;
}

uint32_t resolve_projected_timestamp(uint32_t sync_epoch, uint32_t sync_ms, uint32_t now_ms) {
  if (sync_epoch == 0) {
    return 0;
  }
  return sync_epoch + ((now_ms - sync_ms) / 1000);
}

uint32_t resolve_restored_last_seen_ms(
    uint32_t saved_last_updated, uint32_t current_timestamp, uint32_t now_ms, uint32_t stale_after_ms) {
  if (saved_last_updated == 0 || current_timestamp == 0 || saved_last_updated >= current_timestamp) {
    return now_ms;
  }

  const uint64_t elapsed_ms = static_cast<uint64_t>(current_timestamp - saved_last_updated) * 1000U;
  if (elapsed_ms <= stale_after_ms) {
    return now_ms - static_cast<uint32_t>(elapsed_ms);
  }
  return now_ms - stale_after_ms - 1U;
}

uint32_t unchanged_state_save_interval_ms(uint32_t stale_after_ms) {
  return std::min(DEFAULT_UNCHANGED_STATE_SAVE_INTERVAL_MS, stale_after_ms);
}

bool should_persist_logical_state(
    bool value_changed, uint32_t now_ms, uint32_t previous_save_ms, uint32_t interval_ms) {
  if (value_changed || previous_save_ms == 0) {
    return true;
  }
  return static_cast<uint32_t>(now_ms - previous_save_ms) >= interval_ms;
}

bool matches_mapping(const DecodedPacket &packet, const SensorMapping &mapping) {
  if (matches_key(packet, mapping.primary)) {
    return true;
  }
  return std::any_of(mapping.synonyms.begin(), mapping.synonyms.end(), [&](const SensorKey &synonym) {
    return matches_key(packet, synonym);
  });
}

bool GatewayState::set_mapping(const std::string &logical_key, const std::string &mapping_value) {
  if (trim_ascii_whitespace(mapping_value).empty()) {
    const bool had_mapping = mappings_.erase(logical_key) > 0;
    const bool had_hash = mapping_hashes_.erase(logical_key) > 0;
    logical_states_[logical_key] = LogicalSensorState{};
    return had_mapping || had_hash;
  }
  auto parsed = parse_sensor_mapping(mapping_value);
  if (!parsed.has_value()) {
    ESP_LOGW(TAG, "Ignoring invalid mapping for '%s': '%s'", logical_key.c_str(), mapping_value.c_str());
    return false;
  }
  const auto existing = mappings_.find(logical_key);
  if (existing != mappings_.end() && same_mapping(existing->second, *parsed)) {
    return false;
  }
  mappings_[logical_key] = std::move(*parsed);
  mapping_hashes_[logical_key] = sensor_mapping_hash(format_sensor_mapping(mappings_[logical_key]));
  logical_states_[logical_key] = LogicalSensorState{};
  return true;
}

void GatewayState::restore_logical_state(const std::string &logical_key, const LogicalSensorState &state) {
  if (mappings_.find(logical_key) == mappings_.end()) {
    return;
  }
  logical_states_[logical_key] = state;
}

const LogicalSensorState *GatewayState::logical_sensor(const std::string &logical_key) const {
  auto item = logical_states_.find(logical_key);
  if (item == logical_states_.end()) {
    return nullptr;
  }
  return &item->second;
}

std::optional<uint32_t> GatewayState::mapping_hash(const std::string &logical_key) const {
  const auto existing = mapping_hashes_.find(logical_key);
  if (existing == mapping_hashes_.end()) {
    return {};
  }
  return existing->second;
}

PacketResult GatewayState::process_packet(const DecodedPacket &packet) {
  matched_logical_keys_.clear();
  changed_logical_keys_.clear();
  if (packet.model.empty() || packet.id.empty()) {
    return PacketResult::REJECTED_INVALID;
  }

  bool matched = false;
  for (const auto &[logical_key, mapping] : mappings_) {
    if (!matches_mapping(packet, mapping)) {
      continue;
    }
    auto &state = logical_states_[logical_key];
    const bool value_changed = !state.has_value || !same_persisted_values(state, packet);
    state.has_value = true;
    state.temperature_f = packet.temperature_f;
    state.humidity = packet.humidity;
    state.battery = packet.battery;
    state.rssi = packet.rssi;
    state.last_seen_ms = packet.seen_ms;
    matched_logical_keys_.push_back(logical_key);
    if (value_changed) {
      changed_logical_keys_.push_back(logical_key);
    }
    matched = true;
  }

  if (matched) {
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

bool GatewayState::is_stale(const std::string &logical_key, uint32_t now_ms) const {
  const auto *state = logical_sensor(logical_key);
  if (state == nullptr || !state->has_value) {
    return true;
  }
  return static_cast<uint32_t>(now_ms - state->last_seen_ms) > stale_after_ms_;
}

std::optional<uint32_t> GatewayState::next_stale_state_publish_delay_ms(uint32_t now_ms) const {
  std::optional<uint32_t> next_delay;
  for (const auto &entry : logical_states_) {
    const auto &state = entry.second;
    if (!state.has_value) {
      continue;
    }
    const uint32_t elapsed_ms = static_cast<uint32_t>(now_ms - state.last_seen_ms);
    if (elapsed_ms > stale_after_ms_) {
      continue;
    }
    const uint32_t delay_ms = stale_after_ms_ - elapsed_ms;
    if (!next_delay.has_value() || delay_ms < *next_delay) {
      next_delay = delay_ms == 0 ? 1 : delay_ms;
    }
  }
  return next_delay;
}

void GatewayState::record_candidate(const DecodedPacket &packet, bool matched_known) {
  prune_candidates(packet.seen_ms);

  SensorKey key{packet.model, packet.channel, packet.id};
  auto existing = std::find_if(candidates_.begin(), candidates_.end(), [&](const CandidateRow &row) {
    return same_key(row.key, key);
  });

  if (existing == candidates_.end()) {
    CandidateRow row = make_candidate_row(packet, matched_known);
    const auto insertion_point =
        std::lower_bound(candidates_.begin(), candidates_.end(), row, candidate_less);
    candidates_.insert(insertion_point, std::move(row));
    if (candidates_.size() > candidate_limit_) {
      candidates_.resize(candidate_limit_);
    }
    return;
  }

  const CandidateRow previous_row = *existing;
  candidates_.erase(existing);
  CandidateRow updated = make_candidate_row(packet, matched_known);
  updated.first_seen_ms = previous_row.first_seen_ms;
  updated.packet_count = previous_row.packet_count + 1;
  const auto insertion_point = std::lower_bound(candidates_.begin(), candidates_.end(), updated, candidate_less);
  candidates_.insert(insertion_point, std::move(updated));

  if (candidates_.size() > candidate_limit_) {
    candidates_.resize(candidate_limit_);
  }
}

void GatewayState::prune_candidates(uint32_t now_ms) {
  candidates_.erase(
      std::remove_if(
          candidates_.begin(),
          candidates_.end(),
          [&](const CandidateRow &row) { return is_older_than(now_ms, row.last_seen_ms, stale_after_ms_); }),
      candidates_.end());
}

}  // namespace esphome::rtl433_native
