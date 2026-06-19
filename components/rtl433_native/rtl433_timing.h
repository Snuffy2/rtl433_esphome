#pragma once

#include <cstddef>
#include <cstdint>
#include <string>
#include <unordered_set>

namespace esphome::rtl433_native {
namespace timing {

constexpr uint32_t kDefaultOperationWarnThresholdMs = 25;
constexpr uint32_t kStartupPacingDelayMs = 25;
constexpr std::size_t kStartupPacingFairnessWindow = 4;

inline uint32_t operation_duration_ms(uint32_t start_ms, uint32_t end_ms) {
  return end_ms - start_ms;
}

inline bool is_operation_too_long(uint32_t start_ms, uint32_t end_ms, uint32_t threshold_ms) {
  return operation_duration_ms(start_ms, end_ms) > threshold_ms;
}

inline uint32_t startup_pacing_delay_ms(bool startup_pacing_active, bool startup_work) {
  return (startup_pacing_active && startup_work) ? kStartupPacingDelayMs : 0;
}

inline bool should_preempt_paced_flush(bool flush_pending, bool flush_paced, bool new_work_paced) {
  return flush_pending && flush_paced && !new_work_paced;
}

inline bool should_use_startup_pacing(
    bool startup_pacing_active, bool has_reprojected_startup_work) {
  return startup_pacing_active || has_reprojected_startup_work;
}

inline bool pending_queue_has_unpaced_work(
    const std::unordered_set<std::string> &pending, const std::unordered_set<std::string> &paced) {
  for (const auto &logical_key : pending) {
    if (paced.find(logical_key) == paced.end()) {
      return true;
    }
  }
  return false;
}

inline bool pending_queue_has_paced_work(
    const std::unordered_set<std::string> &pending, const std::unordered_set<std::string> &paced) {
  for (const auto &logical_key : pending) {
    if (paced.find(logical_key) != paced.end()) {
      return true;
    }
  }
  return false;
}

inline bool should_select_paced_queue_item(
    const std::unordered_set<std::string> &pending, const std::unordered_set<std::string> &paced,
    std::size_t consecutive_unpaced_selections, std::size_t fairness_window = kStartupPacingFairnessWindow) {
  return consecutive_unpaced_selections >= fairness_window &&
         pending_queue_has_paced_work(pending, paced);
}

inline std::string next_pending_queue_key(
    const std::unordered_set<std::string> &pending, const std::unordered_set<std::string> &paced,
    bool prefer_paced = false) {
  if (pending.empty()) {
    return "";
  }
  if (prefer_paced) {
    for (const auto &logical_key : pending) {
      if (paced.find(logical_key) != paced.end()) {
        return logical_key;
      }
    }
  }
  for (const auto &logical_key : pending) {
    if (paced.find(logical_key) == paced.end()) {
      return logical_key;
    }
  }
  return *pending.begin();
}

}  // namespace timing
}  // namespace esphome::rtl433_native
