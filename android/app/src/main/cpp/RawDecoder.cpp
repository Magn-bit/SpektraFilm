#include "RawDecoder.h"

#include <libraw/libraw.h>

#include <algorithm>
#include <cerrno>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <limits>
#include <memory>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>

namespace spektra {
namespace {

struct ProgressState {
    const std::atomic<bool>& cancelled;
    const RawProgress& callback;
    double last = 0;
    bool callbackCancelled = false;

    void report(const char* stage, double fraction) {
        if (cancelled.load(std::memory_order_relaxed) || callbackCancelled)
            throw RawError(RawErrorKind::Cancelled, "RAW development cancelled");
        last = std::max(last, std::min(1.0, fraction));
        if (callback && !callback(stage, last)) {
            callbackCancelled = true;
            throw RawError(RawErrorKind::Cancelled, "RAW development cancelled");
        }
    }
};

int progressCallback(void* opaque, LibRaw_progress stage, int iteration, int expected) {
    auto& state = *static_cast<ProgressState*>(opaque);
    if (state.cancelled.load(std::memory_order_relaxed) || state.callbackCancelled)
        return 1;
    const double inner = expected > 0 ? std::clamp(double(iteration) / expected, 0.0, 1.0) : 0;
    double fraction = 0.02;
    if (stage >= LIBRAW_PROGRESS_LOAD_RAW) fraction = 0.05 + 0.20 * inner;
    if (stage >= LIBRAW_PROGRESS_RAW2_IMAGE) fraction = 0.25;
    if (stage >= LIBRAW_PROGRESS_SCALE_COLORS) fraction = 0.30 + 0.08 * inner;
    if (stage >= LIBRAW_PROGRESS_PRE_INTERPOLATE) fraction = 0.38;
    if (stage >= LIBRAW_PROGRESS_INTERPOLATE) fraction = 0.40 + 0.28 * inner;
    if (stage >= LIBRAW_PROGRESS_MIX_GREEN) fraction = 0.68;
    if (stage >= LIBRAW_PROGRESS_HIGHLIGHTS) fraction = 0.70 + 0.05 * inner;
    if (stage >= LIBRAW_PROGRESS_CONVERT_RGB) fraction = 0.78 + 0.04 * inner;
    try {
        state.report(LibRaw::strprogress(stage), fraction);
        return 0;
    } catch (...) {
        // Never unwind through LibRaw's C callback. The caller rethrows its own
        // cancellation after LibRaw releases its internal processing buffers.
        state.callbackCancelled = true;
        return 1;
    }
}

void checkResult(int code, const char* operation, const ProgressState& state) {
    if (state.cancelled.load(std::memory_order_relaxed) || state.callbackCancelled ||
        code == LIBRAW_CANCELLED_BY_CALLBACK)
        throw RawError(RawErrorKind::Cancelled, "RAW development cancelled");
    if (code == LIBRAW_SUCCESS) return;
    RawErrorKind kind = RawErrorKind::Io;
    if (code == LIBRAW_FILE_UNSUPPORTED || code == LIBRAW_NOT_IMPLEMENTED ||
        code == LIBRAW_REQUEST_FOR_NONEXISTENT_IMAGE)
        kind = RawErrorKind::Unsupported;
    if (code == LIBRAW_UNSUFFICIENT_MEMORY || code == LIBRAW_TOO_BIG)
        kind = RawErrorKind::Memory;
    const char* reason = LibRaw::strerror(code);
    throw RawError(kind, std::string(operation) + ": " +
                         (reason ? reason : "Unknown LibRaw error") +
                         " (" + std::to_string(code) + ")");
}

void validateSource(const std::string& sourcePath) {
    struct stat status{};
    if (sourcePath.empty() || sourcePath.front() != '/')
        throw RawError(RawErrorKind::Invalid, "RAW source must be an absolute local file path");
    if (stat(sourcePath.c_str(), &status) || !S_ISREG(status.st_mode))
        throw RawError(RawErrorKind::Io, "RAW source is not a readable regular file");
}

// These are the official LibRaw output parameters. The default BT.709 transfer
// must be overridden explicitly: downstream code consumes encoded sRGB.
void configure(LibRaw& raw, bool halfSize, ProgressState& progress) {
    raw.imgdata.params.use_camera_wb = 1;
    raw.imgdata.params.use_auto_wb = 0;
    raw.imgdata.params.output_color = 1;  // sRGB primaries
    raw.imgdata.params.output_bps = 16;
    raw.imgdata.params.gamm[0] = 1.0 / 2.4;
    raw.imgdata.params.gamm[1] = 12.92;
    // Reconstruction (>2) disables LibRaw histogram auto-bright regardless
    // of no_auto_bright. Blend preserves highlight handling and enables it.
    raw.imgdata.params.highlight = 2;     // LibRaw Blend
    raw.imgdata.params.no_auto_bright = 0;
    raw.imgdata.params.auto_bright_thr = 0.01;
    raw.imgdata.params.bright = 1.0;
    raw.imgdata.params.half_size = halfSize ? 1 : 0;
    raw.imgdata.params.user_qual = 3;     // AHD, mature full-size Bayer path
    raw.imgdata.params.user_flip = -1;   // honor camera orientation
    raw.imgdata.params.four_color_rgb = 0;
    raw.imgdata.rawparams.use_rawspeed = 0;
    raw.imgdata.rawparams.use_dngsdk = 0;
    // Bound LibRaw's checked RAW/unpack allocations, not total process RSS.
    // Kotlin separately admits jobs against system memory without downsampling.
    raw.imgdata.rawparams.max_raw_memory_mb = 512;
    raw.set_progress_handler(progressCallback, &progress);
}

// Match LibRaw::copy_mem_image's histogram/white-point curve setup, while
// retaining row output instead of a second full-frame RGB allocation. Merely
// choosing Blend is insufficient if the gamma white stays fixed at 65536.
class RowRaw final : public LibRaw {
public:
    void prepareOutputCurve() {
        const auto* histogram = libraw_internal_data.output_data.histogram;
        if (!histogram) return;  // copy_mem_image leaves the existing curve.
        const auto& parameters = imgdata.params;
        int percentile = int(imgdata.sizes.width * imgdata.sizes.height *
                             parameters.auto_bright_thr);
        if (libraw_internal_data.internal_output_params.fuji_width)
            percentile /= 2;
        int white = 0x2000;
        if (!((parameters.highlight & ~2) || parameters.no_auto_bright)) {
            white = 0;
            for (int channel = 0; channel < imgdata.idata.colors; ++channel) {
                int total = 0, value = 0x2000;
                while (--value > 32)
                    if ((total += histogram[channel][value]) > percentile)
                        break;
                white = std::max(white, value);
            }
        }
        gamma_curve(parameters.gamm[0], parameters.gamm[1], 2,
                    int((white << 3) / parameters.bright));
    }
};

class PendingOutput {
public:
    explicit PendingOutput(const std::string& destination) : destination_(destination) {
        if (destination.empty() || destination.front() != '/')
            throw RawError(RawErrorKind::Invalid, "RAW output must be an absolute local file path");
        std::string pattern = destination + ".part.XXXXXX";
        std::vector<char> path(pattern.begin(), pattern.end());
        path.push_back('\0');
        int descriptor = mkstemp(path.data());  // mode 0600; same filesystem as destination
        if (descriptor < 0)
            throw RawError(RawErrorKind::Io, "Cannot create private RAW cache: " +
                                             std::string(std::strerror(errno)));
        temporary_ = path.data();
        file_ = fdopen(descriptor, "wb");
        if (!file_) {
            close(descriptor);
            std::remove(temporary_.c_str());
            throw RawError(RawErrorKind::Io, "Cannot open RAW cache stream");
        }
    }

    ~PendingOutput() {
        if (file_) std::fclose(file_);
        if (!temporary_.empty()) std::remove(temporary_.c_str());
    }
    PendingOutput(const PendingOutput&) = delete;
    PendingOutput& operator=(const PendingOutput&) = delete;

    void write(const std::vector<unsigned char>& row) {
        if (std::fwrite(row.data(), 1, row.size(), file_) != row.size())
            throw RawError(RawErrorKind::Io, "Cannot write RAW RGB16 cache: " +
                                             std::string(std::strerror(errno)));
    }

    void commit() {
        if (std::fflush(file_) || fsync(fileno(file_)))
            throw RawError(RawErrorKind::Io, "Cannot flush RAW RGB16 cache");
        FILE* closing = file_;
        file_ = nullptr;
        if (std::fclose(closing))
            throw RawError(RawErrorKind::Io, "Cannot close RAW RGB16 cache");
        if (std::rename(temporary_.c_str(), destination_.c_str()))
            throw RawError(RawErrorKind::Io, "Cannot publish RAW RGB16 cache: " +
                                             std::string(std::strerror(errno)));
        temporary_.clear();
    }

private:
    std::string destination_;
    std::string temporary_;
    FILE* file_ = nullptr;
};

}  // namespace

RawInfo inspectRaw(const std::string& sourcePath, const std::atomic<bool>& cancelled,
                   const RawProgress& callback) {
    validateSource(sourcePath);
    ProgressState progress{cancelled, callback};
    auto decoder = std::make_unique<RowRaw>();
    auto& raw = *decoder;
    configure(raw, false, progress);
    progress.report("Reading RAW metadata", 0);
    checkResult(raw.open_file(sourcePath.c_str()), "Opening RAW", progress);
    RawInfo result;
    result.rawWidth = raw.imgdata.sizes.raw_width;
    result.rawHeight = raw.imgdata.sizes.raw_height;
    result.flip = raw.imgdata.sizes.flip;
    checkResult(raw.adjust_sizes_info_only(), "Reading RAW dimensions", progress);
    result.width = raw.imgdata.sizes.iwidth;
    result.height = raw.imgdata.sizes.iheight;
    if (result.width <= 0 || result.height <= 0)
        throw RawError(RawErrorKind::Unsupported, "RAW has no usable full-resolution dimensions");
    progress.report("RAW metadata ready", 1);
    return result;
}

RawInfo developRaw(const std::string& sourcePath, const std::string& outputPath,
                   bool halfSize, const std::atomic<bool>& cancelled,
                   const RawProgress& callback) {
    validateSource(sourcePath);
    if (sourcePath == outputPath)
        throw RawError(RawErrorKind::Invalid, "RAW source and output paths must differ");
    // Do not overwrite a hard-link/symlink to the source file either.
    struct stat source{}, destination{};
    if (!stat(sourcePath.c_str(), &source) && !stat(outputPath.c_str(), &destination) &&
        source.st_dev == destination.st_dev && source.st_ino == destination.st_ino)
        throw RawError(RawErrorKind::Invalid, "RAW output refers to the source file");
    ProgressState progress{cancelled, callback};
    auto decoder = std::make_unique<RowRaw>();
    auto& raw = *decoder;
    configure(raw, halfSize, progress);
    progress.report("Opening RAW", 0);
    checkResult(raw.open_file(sourcePath.c_str()), "Opening RAW", progress);
    RawInfo result;
    result.rawWidth = raw.imgdata.sizes.raw_width;
    result.rawHeight = raw.imgdata.sizes.raw_height;
    result.flip = raw.imgdata.sizes.flip;
    progress.report("Unpacking full RAW data", 0.04);
    checkResult(raw.unpack(), "Unpacking RAW", progress);
    if (raw.error_count() != 0)
        throw RawError(RawErrorKind::Io, "RAW contains damaged or truncated pixel data");
    progress.report("Developing RAW", 0.25);
    checkResult(raw.dcraw_process(), "Developing RAW", progress);
    int colors = 0, bits = 0;
    raw.get_mem_image_format(&result.width, &result.height, &colors, &bits);
    if (!raw.imgdata.image || result.width <= 0 || result.height <= 0 ||
        colors != 3 || bits != 16)
        throw RawError(RawErrorKind::Unsupported, "RAW decoder did not produce 3-channel RGB16");

    const int sourceWidth = raw.imgdata.sizes.width;
    const int sourceHeight = raw.imgdata.sizes.height;
    const int flip = raw.imgdata.sizes.flip;
    if (flip < 0 || flip > 7 || sourceWidth <= 0 || sourceHeight <= 0 ||
        result.width != ((flip & 4) ? sourceHeight : sourceWidth) ||
        result.height != ((flip & 4) ? sourceWidth : sourceHeight))
        throw RawError(RawErrorKind::Unsupported, "Unsupported RAW output orientation");
    if (size_t(result.width) > std::numeric_limits<size_t>::max() / 6)
        throw RawError(RawErrorKind::Memory, "RAW scanline is too large");

    raw.prepareOutputCurve();
    std::vector<unsigned char> row(size_t(result.width) * 6);
    PendingOutput output(outputPath);
    for (int y = 0; y < result.height; ++y) {
        if ((y & 15) == 0)
            progress.report("Writing RGB16 cache", 0.84 + 0.15 * double(y) / result.height);
        for (int x = 0; x < result.width; ++x) {
            // LibRaw::flip_index mapping, with original unrotated dimensions.
            // Works for all eight mirrored/transposed TIFF orientations.
            int sy = (flip & 4) ? x : y;
            int sx = (flip & 4) ? y : x;
            if (flip & 2) sy = sourceHeight - 1 - sy;
            if (flip & 1) sx = sourceWidth - 1 - sx;
            const auto& pixel = raw.imgdata.image[size_t(sy) * sourceWidth + sx];
            for (int channel = 0; channel < 3; ++channel) {
                const unsigned short value = raw.imgdata.color.curve[pixel[channel]];
                const size_t offset = size_t(x) * 6 + channel * 2;
                row[offset] = static_cast<unsigned char>(value & 0xff);
                row[offset + 1] = static_cast<unsigned char>(value >> 8);
            }
        }
        output.write(row);
    }
    progress.report("Finishing RGB16 cache", 0.995);
    output.commit();
    return result;
}

const char* rawVersion() { return LibRaw::version(); }

bool rawCameraSupported(const std::string& camera) {
    const char** cameras = LibRaw::cameraList();
    for (int i = 0; cameras && cameras[i]; ++i)
        if (camera == cameras[i]) return true;
    return false;
}

}  // namespace spektra
