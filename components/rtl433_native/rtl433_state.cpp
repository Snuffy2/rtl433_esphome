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

bool candidate_less(const CandidateRow &left, const CandidateRow &right) {
  if (left.last_seen_ms != right.last_seen_ms) {
    return left.last_seen_ms > right.last_seen_ms;
  }
  return key_less(left.key, right.key);
}

bool is_older_than(uint32_t now_ms, uint32_t seen_ms, uint32_t age_ms) {
  return static_cast<uint32_t>(now_ms - seen_ms) > age_ms;
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

bool matches_mapping(const DecodedPacket &packet, const SensorMapping &mapping) {
  if (matches_key(packet, mapping.primary)) {
    return true;
  }
  return std::any_of(mapping.synonyms.begin(), mapping.synonyms.end(), [&](const SensorKey &synonym) {
    return matches_key(packet, synonym);
  });
}

void GatewayState::set_mapping(const std::string &logical_key, const std::string &mapping_value) {
  auto parsed = parse_sensor_mapping(mapping_value);
  if (!parsed.has_value()) {
    ESP_LOGW(TAG, "Removing mapping for '%s' due to invalid mapping '%s'", logical_key.c_str(), mapping_value.c_str());
    mappings_.erase(logical_key);
    logical_states_.erase(logical_key);
    return;
  }
  const auto existing = mappings_.find(logical_key);
  if (existing != mappings_.end() && same_mapping(existing->second, *parsed)) {
    return;
  }
  mappings_[logical_key] = std::move(*parsed);
  logical_states_[logical_key] = LogicalSensorState{};
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

PacketResult GatewayState::process_packet(const DecodedPacket &packet) {
  if (packet.model.empty() || packet.id.empty()) {
    return PacketResult::REJECTED_INVALID;
  }

  bool matched = false;
  for (const auto &[logical_key, mapping] : mappings_) {
    if (!matches_mapping(packet, mapping)) {
      continue;
    }
    auto &state = logical_states_[logical_key];
    state.has_value = true;
    state.temperature_f = packet.temperature_f;
    state.humidity = packet.humidity;
    state.battery = packet.battery;
    state.rssi = packet.rssi;
    state.last_seen_ms = packet.seen_ms;
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

void GatewayState::record_candidate(const DecodedPacket &packet, bool matched_known) {
  prune_candidates(packet.seen_ms);

  SensorKey key{packet.model, packet.channel, packet.id};
  auto existing = std::find_if(candidates_.begin(), candidates_.end(), [&](const CandidateRow &row) {
    return same_key(row.key, key);
  });

  if (existing == candidates_.end()) {
    CandidateRow row;
    row.key = key;
    row.first_seen_ms = packet.seen_ms;
    candidates_.push_back(row);
    existing = std::prev(candidates_.end());
  }

  existing->temperature_f = packet.temperature_f;
  existing->humidity = packet.humidity;
  existing->battery = packet.battery;
  existing->rssi = packet.rssi;
  existing->last_seen_ms = packet.seen_ms;
  existing->packet_count += 1;
  existing->matched_known = matched_known;

  std::sort(candidates_.begin(), candidates_.end(), candidate_less);

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
