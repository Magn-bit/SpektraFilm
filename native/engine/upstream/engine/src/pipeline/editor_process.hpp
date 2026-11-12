#pragma once
#include "gpu/gpu.hpp"
#include "json.hpp"
#include "colour.hpp"
#include "spektrafilm/spk_engine.h"

namespace spk::editor {
// Independent product editing stage. Geometry remains in oriented source
// coordinates and is deliberately applied after this stage by the caller.
bool process(gpu::Gpu* gpu, const Colour& colour, const spk_image& input,
             const Json& request, float* output, double& elapsed_ms,
             std::string& error,const float* tone_base=nullptr);
bool defringe(gpu::Gpu* gpu,const spk_image& input,float* output,
              uint64_t& changed_pixels,double& elapsed_ms,std::string& error);
}
