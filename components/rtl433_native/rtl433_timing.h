#pragma once

#include <cstdint>

namespace esphome::rtl433_native {
namespace timing {

constexpr uint32_t kDefaultOperationWarnThresholdMs = 25;
constexpr uint32_t kStartupPacingDelayMs = 25;

inline uint32_t operation_duration_ms(uint32_t start_ms, uint32_t end_ms) {
  return end_ms - start_ms;
}

inline bool is_operation_too_long(uint32_t start_ms, uint32_t end_ms, uint32_t threshold_ms) {
  return operation_duration_ms(start_ms, end_ms) > threshold_ms;
}

inline uint32_t startup_pacing_delay_ms(bool startup_pacing_active, bool startup_work) {
  return (startup_pacing_active && startup_work) ? kStartupPacingDelayMs : 0;
}

}  // namespace timing
}  // namespace esphome::rtl433_native
