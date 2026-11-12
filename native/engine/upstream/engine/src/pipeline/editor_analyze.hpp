#pragma once
#include "pipeline.hpp"
#include "spektrafilm/spk_engine.h"

namespace spk::editor {
// Stateless analysis for mobile executors that own a Pipeline rather than a
// C-ABI session. Caller serializes GPU use and owns begin_frame/end_frame.
// The input must cover the complete frame (a preview proxy is sufficient).
// Results match spk_solve/spk_scene_latitude JSON and never commit parameters.
bool analyze(gpu::Gpu* gpu, Colour* colour, Blob* blob, SetupCache* cache,
             const Json& neutral_filters, const Params& params,
             const spk_image& input, const std::string& target,
             const Json& request, Json& reply, std::string& error);
}
