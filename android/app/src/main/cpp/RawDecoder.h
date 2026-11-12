#pragma once

#include <atomic>
#include <functional>
#include <stdexcept>
#include <string>

namespace spektra {

enum class RawErrorKind { Io, Unsupported, Cancelled, Invalid, Memory };

class RawError : public std::runtime_error {
public:
    RawError(RawErrorKind kind, const std::string& message)
        : std::runtime_error(message), kind(kind) {}
    RawErrorKind kind;
};

struct RawInfo {
    int width = 0;
    int height = 0;
    int rawWidth = 0;
    int rawHeight = 0;
    int flip = 0;
};

// Called on the same worker thread as inspectRaw/developRaw. Return false to
// cancel. No Java bitmap or full-frame RGB copy crosses this interface.
using RawProgress = std::function<bool(const char* stage, double fraction)>;

RawInfo inspectRaw(const std::string& sourcePath,
                   const std::atomic<bool>& cancelled,
                   const RawProgress& progress = {});

// Atomically publishes a headerless, top-left-oriented RGB16LE file only after
// all rows are written and closed successfully. Source must be a seekable local
// file. halfSize is a preview-only choice; false always processes full RAW data.
RawInfo developRaw(const std::string& sourcePath, const std::string& outputPath,
                   bool halfSize, const std::atomic<bool>& cancelled,
                   const RawProgress& progress = {});

const char* rawVersion();
bool rawCameraSupported(const std::string& camera);

}  // namespace spektra
