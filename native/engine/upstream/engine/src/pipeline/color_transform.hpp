#pragma once
#include <cstdint>
#include <string>
#include "core/json.hpp"
#include "gpu/gpu.hpp"

namespace spk::colour_preview {
// Float samples throughout. Setup JSON and C_max come from the engine's
// cached spk_output_transform; this is not a second colour implementation.
bool transform(gpu::Gpu* gpu,const float* rgb,uint32_t width,uint32_t height,
               const Json& setup,const float* cmax,uint32_t cmax_count,
               float* output,std::string& error);
}
