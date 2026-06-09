#include <cmath>
#include <cstdlib>
#include <iostream>
#include <string>

#include "components/rtl433_native/rtl433_state.h"

namespace {

namespace rtl433 = esphome::rtl433_native;

void require(bool condition, const std::string &message) {
  if (!condition) {
    std::cerr << message << '\n';
    std::exit(1);
  }
}

void test_key_parsing() {
  auto key = rtl433::parse_sensor_key("LaCrosse-TX141THBv2/0/203");
  require(key.has_value(), "expected valid LaCrosse key");
  require(key->model == "LaCrosse-TX141THBv2", "wrong parsed model");
  require(key->channel == "0", "wrong parsed channel");
  require(key->id == "203", "wrong parsed id");
  require(!rtl433::parse_sensor_key("LaCrosse-TX141THBv2/203").has_value(),
          "expected malformed key to fail");
}

void test_known_packet_updates_logical_sensor() {
  rtl433::GatewayState state;
  state.set_mapping("garage_combo_fridge", "LaCrosse-TX141THBv2/0/203");

  rtl433::DecodedPacket packet;
  packet.model = "LaCrosse-TX141THBv2";
  packet.channel = "0";
  packet.id = "203";
  packet.temperature_f = 34.16f;
  packet.humidity = 10.0f;
  packet.battery = 100.0f;
  packet.rssi = -70;
  packet.seen_ms = 1000;

  auto result = state.process_packet(packet);
  require(result == rtl433::PacketResult::MATCHED_KNOWN, "expected known packet match");

  const auto *logical = state.logical_sensor("garage_combo_fridge");
  require(logical != nullptr, "expected logical sensor state");
  require(std::fabs(logical->temperature_f - 34.16f) < 0.001f, "wrong temperature");
  require(logical->last_seen_ms == 1000, "wrong last seen timestamp");
}

void test_synonym_key_updates_logical_sensor() {
  rtl433::GatewayState state;
  state.set_mapping("garage_combo_freezer", "TFA-303221/2/88;LaCrosse-TX141THBv2/1/88");

  rtl433::DecodedPacket packet;
  packet.model = "LaCrosse-TX141THBv2";
  packet.channel = "1";
  packet.id = "88";
  packet.temperature_f = 0.5f;
  packet.humidity = 44.0f;
  packet.battery = 100.0f;
  packet.rssi = -67;
  packet.seen_ms = 2500;

  auto result = state.process_packet(packet);
  require(result == rtl433::PacketResult::MATCHED_KNOWN, "expected synonym packet match");

  const auto *logical = state.logical_sensor("garage_combo_freezer");
  require(logical != nullptr, "expected logical sensor state");
  require(logical->has_value, "expected synonym packet to update logical sensor");
  require(std::fabs(logical->temperature_f - 0.5f) < 0.001f, "wrong synonym temperature");
  require(logical->last_seen_ms == 2500, "wrong synonym last seen timestamp");
}

void test_mapping_list_updates_from_primary_and_synonym() {
  rtl433::GatewayState state;
  state.set_mapping("garage_combo_freezer", "TFA-303221/2/88;LaCrosse-TX141THBv2/1/88");

  rtl433::DecodedPacket primary_packet;
  primary_packet.model = "TFA-303221";
  primary_packet.channel = "2";
  primary_packet.id = "88";
  primary_packet.temperature_f = 12.25f;
  primary_packet.seen_ms = 1000;
  require(state.process_packet(primary_packet) == rtl433::PacketResult::MATCHED_KNOWN,
          "expected primary mapping list key to match");

  rtl433::DecodedPacket synonym_packet;
  synonym_packet.model = "LaCrosse-TX141THBv2";
  synonym_packet.channel = "1";
  synonym_packet.id = "88";
  synonym_packet.temperature_f = 13.5f;
  synonym_packet.seen_ms = 2000;
  require(state.process_packet(synonym_packet) == rtl433::PacketResult::MATCHED_KNOWN,
          "expected synonym mapping list key to match");

  const auto *logical = state.logical_sensor("garage_combo_freezer");
  require(logical != nullptr, "expected logical sensor state");
  require(logical->has_value, "expected mapping list packet to update logical sensor");
  require(std::fabs(logical->temperature_f - 13.5f) < 0.001f, "wrong mapping list temperature");
  require(logical->last_seen_ms == 2000, "wrong mapping list last seen timestamp");
}

void test_spaced_mapping_list_updates_from_synonym() {
  rtl433::GatewayState state;
  state.set_mapping("garage_combo_freezer", " TFA-303221/2/88 ; LaCrosse-TX141THBv2/1/88 ");

  rtl433::DecodedPacket packet;
  packet.model = "LaCrosse-TX141THBv2";
  packet.channel = "1";
  packet.id = "88";
  packet.temperature_f = 14.75f;
  packet.seen_ms = 3000;

  require(state.process_packet(packet) == rtl433::PacketResult::MATCHED_KNOWN,
          "expected whitespace-padded synonym mapping to match");
  const auto *logical = state.logical_sensor("garage_combo_freezer");
  require(logical != nullptr, "expected logical state for spaced mapping");
  require(logical->has_value, "expected spaced synonym packet to update logical sensor");
  require(std::fabs(logical->temperature_f - 14.75f) < 0.001f, "wrong spaced mapping temperature");
}

void test_slash_spaced_mapping_list_updates_from_synonym() {
  rtl433::GatewayState state;
  state.set_mapping("garage_combo_freezer", "TFA-303221 / 2 / 88 ; LaCrosse-TX141THBv2 / 1 / 88");

  rtl433::DecodedPacket packet;
  packet.model = "LaCrosse-TX141THBv2";
  packet.channel = "1";
  packet.id = "88";
  packet.temperature_f = 15.75f;
  packet.seen_ms = 3500;

  require(state.process_packet(packet) == rtl433::PacketResult::MATCHED_KNOWN,
          "expected slash-padded synonym mapping to match");
  const auto *logical = state.logical_sensor("garage_combo_freezer");
  require(logical != nullptr, "expected logical state for slash-spaced mapping");
  require(logical->has_value, "expected slash-spaced synonym packet to update logical sensor");
  require(std::fabs(logical->temperature_f - 15.75f) < 0.001f, "wrong slash-spaced mapping temperature");
}

void test_remapping_clears_old_reading() {
  rtl433::GatewayState state;
  state.set_mapping("garage_combo_fridge", "LaCrosse-TX141THBv2/0/203");

  rtl433::DecodedPacket original_packet;
  original_packet.model = "LaCrosse-TX141THBv2";
  original_packet.channel = "0";
  original_packet.id = "203";
  original_packet.temperature_f = 34.16f;
  original_packet.seen_ms = 1000;

  require(state.process_packet(original_packet) == rtl433::PacketResult::MATCHED_KNOWN,
          "expected initial packet match");

  const auto *before = state.logical_sensor("garage_combo_fridge");
  require(before != nullptr, "expected logical sensor state before remap");
  require(before->has_value, "expected value after first update");

  state.set_mapping("garage_combo_fridge", "LaCrosse-TX141THBv2/1/204");

  const auto *after_remap = state.logical_sensor("garage_combo_fridge");
  require(after_remap != nullptr, "expected logical sensor state after remap");
  require(!after_remap->has_value, "expected remap to clear old reading");
  require(after_remap->last_seen_ms == 0, "expected remap to clear old timestamp");

  require(state.process_packet(original_packet) == rtl433::PacketResult::IGNORED_UNKNOWN,
          "expected old packet key to no longer match");
  const auto *after_old_packet = state.logical_sensor("garage_combo_fridge");
  require(after_old_packet != nullptr, "expected logical sensor state after old packet");
  require(!after_old_packet->has_value, "expected stale state to remain cleared after non-match");
}

void test_reapplying_same_mapping_preserves_restored_reading() {
  rtl433::GatewayState state;
  state.set_mapping("garage_freezer_2", "Acurite-986/2F/31274");

  rtl433::LogicalSensorState restored;
  restored.has_value = true;
  restored.temperature_f = 11.0f;
  restored.battery = 100.0f;
  restored.rssi = -87;
  restored.last_seen_ms = 2000;
  state.restore_logical_state("garage_freezer_2", restored);

  state.set_mapping("garage_freezer_2", "Acurite-986/2F/31274");

  const auto *after = state.logical_sensor("garage_freezer_2");
  require(after != nullptr, "expected logical sensor state after same mapping");
  require(after->has_value, "expected same mapping to preserve restored reading");
  require(after->last_seen_ms == 2000, "expected same mapping to preserve last seen timestamp");
  require(!state.is_stale("garage_freezer_2", 3000), "expected restored reading to remain fresh");
}

void test_reordered_synonyms_preserve_restored_reading() {
  rtl433::GatewayState state;
  state.set_mapping("garage_combo_freezer", "TFA-303221/2/88;LaCrosse-TX141THBv2/1/88;Acurite-986/2F/31274");

  rtl433::LogicalSensorState restored;
  restored.has_value = true;
  restored.temperature_f = 9.5f;
  restored.last_seen_ms = 4000;
  state.restore_logical_state("garage_combo_freezer", restored);

  state.set_mapping("garage_combo_freezer", "TFA-303221/2/88;Acurite-986/2F/31274;LaCrosse-TX141THBv2/1/88");

  const auto *after = state.logical_sensor("garage_combo_freezer");
  require(after != nullptr, "expected logical sensor state after reordered synonyms");
  require(after->has_value, "expected reordered synonyms to preserve restored reading");
  require(after->last_seen_ms == 4000, "expected reordered synonyms to preserve last seen timestamp");
}

void test_reordered_primary_preserves_restored_reading() {
  rtl433::GatewayState state;
  state.set_mapping("garage_combo_freezer", "TFA-303221/2/88;LaCrosse-TX141THBv2/1/88");

  rtl433::LogicalSensorState restored;
  restored.has_value = true;
  restored.temperature_f = 8.25f;
  restored.last_seen_ms = 5000;
  state.restore_logical_state("garage_combo_freezer", restored);

  state.set_mapping("garage_combo_freezer", "LaCrosse-TX141THBv2/1/88;TFA-303221/2/88");

  const auto *after = state.logical_sensor("garage_combo_freezer");
  require(after != nullptr, "expected logical sensor state after reordered primary");
  require(after->has_value, "expected reordered primary to preserve restored reading");
  require(after->last_seen_ms == 5000, "expected reordered primary to preserve last seen timestamp");
}

void test_spaced_reordered_mapping_preserves_restored_reading() {
  rtl433::GatewayState state;
  state.set_mapping("garage_combo_freezer", "TFA-303221/2/88;LaCrosse-TX141THBv2/1/88");

  rtl433::LogicalSensorState restored;
  restored.has_value = true;
  restored.temperature_f = 8.25f;
  restored.last_seen_ms = 5000;
  state.restore_logical_state("garage_combo_freezer", restored);

  state.set_mapping("garage_combo_freezer", " LaCrosse-TX141THBv2/1/88 ; TFA-303221/2/88 ");

  const auto *after = state.logical_sensor("garage_combo_freezer");
  require(after != nullptr, "expected logical sensor state after spaced mapping");
  require(after->has_value, "expected spaced reordered mapping to preserve restored reading");
  require(after->last_seen_ms == 5000, "expected spaced mapping to preserve last seen timestamp");
}

void test_invalid_mapping_input_clears_state_and_mapping() {
  rtl433::GatewayState state;
  state.set_mapping("garage_combo_fridge", "LaCrosse-TX141THBv2/0/203");

  rtl433::DecodedPacket packet;
  packet.model = "LaCrosse-TX141THBv2";
  packet.channel = "0";
  packet.id = "203";
  packet.temperature_f = 34.16f;
  require(state.process_packet(packet) == rtl433::PacketResult::MATCHED_KNOWN,
          "expected known match");

  state.set_mapping("garage_combo_fridge", "not_a_valid_key");
  require(state.logical_sensor("garage_combo_fridge") == nullptr,
          "expected invalid mapping to remove logical state");
  require(state.process_packet(packet) == rtl433::PacketResult::IGNORED_UNKNOWN,
          "expected stale mapping to be removed after invalid mapping input");
}

void test_duplicate_mappings_update_both() {
  rtl433::GatewayState state;
  state.set_mapping("garage_combo_fridge", "LaCrosse-TX141THBv2/0/203");
  state.set_mapping("garage_combo_freezer", "LaCrosse-TX141THBv2/0/203");

  rtl433::DecodedPacket packet;
  packet.model = "LaCrosse-TX141THBv2";
  packet.channel = "0";
  packet.id = "203";
  packet.temperature_f = 55.55f;
  packet.humidity = 11.0f;
  packet.battery = 99.0f;
  packet.rssi = -55;
  packet.seen_ms = 1500;

  auto result = state.process_packet(packet);
  require(result == rtl433::PacketResult::MATCHED_KNOWN, "expected duplicate matches to succeed");

  const auto *fridge = state.logical_sensor("garage_combo_fridge");
  const auto *freezer = state.logical_sensor("garage_combo_freezer");
  require(fridge != nullptr, "expected fridge logical state");
  require(freezer != nullptr, "expected freezer logical state");
  require(fridge->has_value && freezer->has_value, "expected both logical sensors to update");
  require(std::fabs(fridge->temperature_f - 55.55f) < 0.001f, "wrong fridge temperature");
  require(std::fabs(freezer->temperature_f - 55.55f) < 0.001f, "wrong freezer temperature");
}

void test_invalid_packet_is_rejected() {
  rtl433::GatewayState state;
  state.set_mapping("garage_combo_fridge", "LaCrosse-TX141THBv2/0/203");

  rtl433::DecodedPacket invalid_model;
  invalid_model.id = "203";
  invalid_model.channel = "0";
  require(state.process_packet(invalid_model) == rtl433::PacketResult::REJECTED_INVALID,
          "expected empty model packet to be rejected");

  rtl433::DecodedPacket invalid_id;
  invalid_id.model = "LaCrosse-TX141THBv2";
  invalid_id.channel = "0";
  require(state.process_packet(invalid_id) == rtl433::PacketResult::REJECTED_INVALID,
          "expected empty id packet to be rejected");
}

void test_unmatched_packet_is_ignored() {
  rtl433::GatewayState state;
  state.set_mapping("garage_combo_fridge", "LaCrosse-TX141THBv2/0/203");

  rtl433::DecodedPacket packet;
  packet.model = "LaCrosse-TX141THBv2";
  packet.channel = "1";
  packet.id = "999";
  require(state.process_packet(packet) == rtl433::PacketResult::IGNORED_UNKNOWN,
          "expected unmatched packet to be ignored");
}

void test_unknowns_only_record_when_discovery_enabled() {
  rtl433::GatewayState state;
  state.set_candidate_limit(10);

  rtl433::DecodedPacket packet;
  packet.model = "Acurite-986";
  packet.channel = "1R";
  packet.id = "11932";
  packet.temperature_f = 75.0f;
  packet.battery = 100.0f;
  packet.rssi = -88;
  packet.seen_ms = 2000;

  require(state.process_packet(packet) == rtl433::PacketResult::IGNORED_UNKNOWN,
          "unknown packet should be ignored while discovery is disabled");
  require(state.candidates().empty(), "candidate table should be empty");

  state.set_discovery_enabled(true);
  require(state.process_packet(packet) == rtl433::PacketResult::RECORDED_CANDIDATE,
          "unknown packet should be recorded while discovery is enabled");
  require(state.candidates().size() == 1, "candidate table should have one row");
  require(state.candidates().front().packet_count == 1, "candidate count should start at one");
}

void test_candidates_are_grouped_capped_and_clearable() {
  rtl433::GatewayState state;
  state.set_discovery_enabled(true);
  state.set_candidate_limit(2);

  for (int index = 0; index < 4; ++index) {
    rtl433::DecodedPacket packet;
    packet.model = "Noise";
    if (index == 2) {
      packet.channel = "1";
      packet.id = "101";
    } else {
      packet.channel = std::to_string(index);
      packet.id = std::to_string(100 + index);
    }
    packet.temperature_f = static_cast<float>(index);
    packet.rssi = -60 - index;
    packet.seen_ms = 1000 + static_cast<uint32_t>(index);
    state.process_packet(packet);
  }

  require(state.candidates().size() == 2, "candidate table should honor limit");
  require(state.candidates().front().last_seen_ms == 1003, "newest candidate should sort first");
  for (const auto &candidate : state.candidates()) {
    if (candidate.key.channel == "1" && candidate.key.id == "101") {
      require(candidate.packet_count == 2, "duplicate packet keys should group into one row");
      require(candidate.last_seen_ms == 1002, "grouped row should hold the latest seen timestamp");
    }
  }

  state.clear_candidates();
  require(state.candidates().empty(), "clear should empty candidate table");
}

void test_duplicate_mappings_record_matched_candidate_once() {
  rtl433::GatewayState state;
  state.set_discovery_enabled(true);
  state.set_mapping("garage_combo_fridge", "LaCrosse-TX141THBv2/0/203");
  state.set_mapping("garage_combo_freezer", "LaCrosse-TX141THBv2/0/203");

  rtl433::DecodedPacket packet;
  packet.model = "LaCrosse-TX141THBv2";
  packet.channel = "0";
  packet.id = "203";
  packet.temperature_f = 55.55f;
  packet.humidity = 11.0f;
  packet.battery = 99.0f;
  packet.rssi = -55;
  packet.seen_ms = 1500;

  auto result = state.process_packet(packet);
  require(result == rtl433::PacketResult::MATCHED_KNOWN, "expected duplicate matches to succeed");

  const auto *fridge = state.logical_sensor("garage_combo_fridge");
  const auto *freezer = state.logical_sensor("garage_combo_freezer");
  require(fridge != nullptr && freezer != nullptr, "expected both logical sensor states");
  require(fridge->has_value && freezer->has_value, "expected both logical sensors to update");
  require(fridge->temperature_f == freezer->temperature_f, "logical sensor temperatures should match");

  require(state.candidates().size() == 1, "duplicate mapped packet should create one matched candidate row");
  require(state.candidates().front().packet_count == 1, "duplicate mapped packet should count as one packet");
}

void test_mapping_override_replaces_default_key() {
  rtl433::GatewayState state;
  state.set_mapping("garage_freezer_1", "Acurite-986/1R/11932");
  state.set_mapping("garage_freezer_1", "Acurite-986/1R/55555");

  rtl433::DecodedPacket old_packet;
  old_packet.model = "Acurite-986";
  old_packet.channel = "1R";
  old_packet.id = "11932";
  old_packet.temperature_f = 75.0f;
  old_packet.seen_ms = 1000;
  require(state.process_packet(old_packet) == rtl433::PacketResult::IGNORED_UNKNOWN,
          "old mapping should no longer match");

  rtl433::DecodedPacket new_packet = old_packet;
  new_packet.id = "55555";
  new_packet.temperature_f = 10.0f;
  new_packet.seen_ms = 2000;
  require(state.process_packet(new_packet) == rtl433::PacketResult::MATCHED_KNOWN,
          "new mapping should match");
}

void test_stale_detection_uses_last_seen() {
  rtl433::GatewayState state;
  state.set_stale_after_ms(600000);
  state.set_mapping("garage_combo_freezer", "TFA-303221/2/88");

  rtl433::DecodedPacket packet;
  packet.model = "TFA-303221";
  packet.channel = "2";
  packet.id = "88";
  packet.temperature_f = 1.22f;
  packet.seen_ms = 1000;
  state.process_packet(packet);

  require(!state.is_stale("garage_combo_freezer", 601000), "exact threshold should not be stale");
  require(!state.is_stale("garage_combo_freezer", 600999), "sensor should not be stale yet");
  require(state.is_stale("garage_combo_freezer", 601001), "sensor should be stale after threshold");
}

void test_stale_detection_wraps_with_uint32_delta() {
  rtl433::GatewayState state;
  state.set_stale_after_ms(1000);
  state.set_mapping("garage_combo_freezer", "Noise/0/1");

  rtl433::DecodedPacket packet;
  packet.model = "Noise";
  packet.channel = "0";
  packet.id = "1";
  packet.seen_ms = 0xFFFFFF00;
  state.process_packet(packet);

  require(!state.is_stale("garage_combo_freezer", 0xFFFFFF80), "post-wrap packets before threshold should not be stale");
  require(state.is_stale("garage_combo_freezer", 0x00000500), "post-wrap packets after threshold should be stale");
}

void test_candidate_order_is_deterministic_for_equal_seen_time() {
  rtl433::GatewayState state;
  state.set_discovery_enabled(true);

  rtl433::DecodedPacket apple;
  apple.model = "Apple";
  apple.channel = "1";
  apple.id = "10";
  apple.seen_ms = 5000;
  state.process_packet(apple);

  rtl433::DecodedPacket zebra;
  zebra.model = "Zebra";
  zebra.channel = "0";
  zebra.id = "1";
  zebra.seen_ms = 5000;
  state.process_packet(zebra);

  require(state.candidates().size() == 2, "candidate table should capture both equal-time rows");
  require(state.candidates().front().key.model == "Apple", "earlier alpha model should sort first for equal last_seen");
  require(state.candidates().front().key.channel == "1", "expected deterministic model order");
  require(state.candidates()[1].key.model == "Zebra", "later alpha model should sort after with equal last_seen");
}

void test_candidates_pruned_by_age() {
  rtl433::GatewayState state;
  state.set_discovery_enabled(true);
  state.set_stale_after_ms(1000);

  rtl433::DecodedPacket old_candidate;
  old_candidate.model = "OldSensor";
  old_candidate.channel = "0";
  old_candidate.id = "111";
  old_candidate.seen_ms = 1000;
  state.process_packet(old_candidate);

  rtl433::DecodedPacket recent_candidate;
  recent_candidate.model = "NewSensor";
  recent_candidate.channel = "0";
  recent_candidate.id = "222";
  recent_candidate.seen_ms = 3000;
  state.process_packet(recent_candidate);

  require(state.candidates().size() == 1, "candidate age window should remove stale rows");
  require(state.candidates().front().key.model == "NewSensor", "only the recent candidate should remain");
}

void test_candidate_age_pruning_is_uint32_wrap_safe() {
  rtl433::GatewayState state;
  state.set_discovery_enabled(true);
  state.set_stale_after_ms(200);

  rtl433::DecodedPacket pre_wrap_candidate;
  pre_wrap_candidate.model = "Rollover";
  pre_wrap_candidate.channel = "0";
  pre_wrap_candidate.id = "001";
  pre_wrap_candidate.seen_ms = 0xFFFFFF80;
  state.process_packet(pre_wrap_candidate);

  rtl433::DecodedPacket post_wrap_candidate;
  post_wrap_candidate.model = "Fresh";
  post_wrap_candidate.channel = "0";
  post_wrap_candidate.id = "002";
  post_wrap_candidate.seen_ms = 0x00000110;
  state.process_packet(post_wrap_candidate);

  require(state.candidates().size() == 1, "uint32 wrap should not prevent age pruning");
  require(state.candidates().front().key.id == "002", "newer wrapped candidate should be retained");
}

}  // namespace

int main() {
  test_key_parsing();
  test_known_packet_updates_logical_sensor();
  test_synonym_key_updates_logical_sensor();
  test_mapping_list_updates_from_primary_and_synonym();
  test_spaced_mapping_list_updates_from_synonym();
  test_slash_spaced_mapping_list_updates_from_synonym();
  test_remapping_clears_old_reading();
  test_reapplying_same_mapping_preserves_restored_reading();
  test_reordered_synonyms_preserve_restored_reading();
  test_reordered_primary_preserves_restored_reading();
  test_spaced_reordered_mapping_preserves_restored_reading();
  test_invalid_mapping_input_clears_state_and_mapping();
  test_duplicate_mappings_update_both();
  test_invalid_packet_is_rejected();
  test_unmatched_packet_is_ignored();
  test_unknowns_only_record_when_discovery_enabled();
  test_candidates_are_grouped_capped_and_clearable();
  test_duplicate_mappings_record_matched_candidate_once();
  test_mapping_override_replaces_default_key();
  test_stale_detection_uses_last_seen();
  test_stale_detection_wraps_with_uint32_delta();
  test_candidate_order_is_deterministic_for_equal_seen_time();
  test_candidates_pruned_by_age();
  test_candidate_age_pruning_is_uint32_wrap_safe();
  return 0;
}
