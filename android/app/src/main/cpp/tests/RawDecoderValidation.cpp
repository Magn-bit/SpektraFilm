#include "RawDecoder.h"
#include <libraw/libraw.h>

#include <algorithm>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <memory>
#include <vector>

namespace fs = std::filesystem;

static void require(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error(message);
}

static void put16(std::vector<unsigned char>& bytes, size_t at, unsigned value) {
    bytes.at(at) = value & 255;
    bytes.at(at + 1) = (value >> 8) & 255;
}

static void put32(std::vector<unsigned char>& bytes, size_t at, unsigned value) {
    put16(bytes, at, value);
    put16(bytes, at + 2, value >> 16);
}

static std::vector<unsigned char> shorts(std::initializer_list<unsigned> values) {
    std::vector<unsigned char> out(values.size() * 2);
    size_t at = 0;
    for (unsigned value : values) { put16(out, at, value); at += 2; }
    return out;
}

static std::vector<unsigned char> longs(std::initializer_list<unsigned> values) {
    std::vector<unsigned char> out(values.size() * 4);
    size_t at = 0;
    for (unsigned value : values) { put32(out, at, value); at += 4; }
    return out;
}

static std::vector<unsigned char> ascii(const char* value) {
    return {value, value + std::strlen(value) + 1};
}

// A small uncompressed, genuine CFA DNG with asymmetric pixel content. This
// exercises decoding/demosaic/transfer/rotation rather than a mock pixel buffer.
static void syntheticDng(const fs::path& path, unsigned orientation, double exposureScale = 1.0) {
    struct Tag { unsigned id, type, count; std::vector<unsigned char> data; };
    std::vector<Tag> tags = {
        {254,4,1,longs({0})}, {256,4,1,longs({96})}, {257,4,1,longs({64})},
        {258,3,1,shorts({16})}, {259,3,1,shorts({1})}, {262,3,1,shorts({32803})},
        {271,2,8,ascii("Spektra")}, {272,2,14,ascii("Synthetic DNG")},
        {273,4,1,longs({0})}, {274,3,1,shorts({orientation})},
        {277,3,1,shorts({1})}, {278,4,1,longs({64})}, {279,4,1,longs({96*64*2})},
        {284,3,1,shorts({1})}, {33421,3,2,shorts({2,2})},
        {33422,1,4,{0,1,1,2}}, {50706,1,4,{1,4,0,0}}, {50707,1,4,{1,1,0,0}},
        {50708,2,14,ascii("Synthetic DNG")}, {50710,1,3,{0,1,2}},
        {50711,3,1,shorts({1})}, {50713,3,2,shorts({1,1})},
        {50714,5,1,longs({64,1})}, {50717,4,1,longs({16383})},
        {50721,10,9,longs({1,1,0,1,0,1,0,1,1,1,0,1,0,1,0,1,1,1})},
        {50728,5,3,longs({1,2,1,1,2,3})}, {50778,3,1,shorts({21})}
    };
    std::sort(tags.begin(), tags.end(), [](const auto& a, const auto& b) { return a.id < b.id; });
    std::vector<unsigned char> bytes(8 + 2 + tags.size() * 12 + 4);
    bytes[0] = bytes[1] = 'I'; put16(bytes, 2, 42); put32(bytes, 4, 8);
    put16(bytes, 8, tags.size());
    size_t stripEntry = 0;
    for (size_t i = 0; i < tags.size(); ++i) {
        const auto& tag = tags[i];
        const size_t entry = 10 + i * 12;
        put16(bytes, entry, tag.id); put16(bytes, entry + 2, tag.type);
        put32(bytes, entry + 4, tag.count);
        if (tag.id == 273) stripEntry = entry + 8;
        if (tag.data.size() <= 4) {
            std::copy(tag.data.begin(), tag.data.end(), bytes.begin() + entry + 8);
        } else {
            if (bytes.size() & 1) bytes.push_back(0);
            put32(bytes, entry + 8, bytes.size());
            bytes.insert(bytes.end(), tag.data.begin(), tag.data.end());
        }
    }
    if (bytes.size() & 1) bytes.push_back(0);
    put32(bytes, stripEntry, bytes.size());
    const size_t pixelStart = bytes.size(); bytes.resize(pixelStart + 96 * 64 * 2);
    for (unsigned y = 0; y < 64; ++y)
        for (unsigned x = 0; x < 96; ++x) {
            unsigned signal = 900 + x * 70 + y * 35 + ((x ^ y) & 7) * 113;
            if ((y & 1) && (x & 1)) signal += 1000;
            signal = 64 + unsigned((signal - 64) * exposureScale + .5);
            put16(bytes, pixelStart + (y * 96 + x) * 2, signal);
        }
    std::ofstream stream(path, std::ios::binary);
    stream.write(reinterpret_cast<const char*>(bytes.data()), bytes.size());
    require(bool(stream), "Cannot create synthetic DNG");
}

static std::vector<unsigned char> readBytes(const fs::path& path) {
    std::ifstream input(path, std::ios::binary);
    require(bool(input), "Cannot read output cache");
    return {std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>()};
}

static void configureReference(LibRaw& reference, bool half, int highlight = 2) {
    auto& p = reference.imgdata.params;
    p.use_camera_wb = 1; p.use_auto_wb = 0;
    p.output_color = 1; p.output_bps = 16;
    p.gamm[0] = 1.0 / 2.4; p.gamm[1] = 12.92;
    p.highlight = highlight; p.no_auto_bright = 0; p.auto_bright_thr = .01;
    p.bright = 1.0;
    p.half_size = half ? 1 : 0; p.user_qual = 3; p.user_flip = -1;
    p.four_color_rgb = 0;
    reference.imgdata.rawparams.use_rawspeed = 0;
    reference.imgdata.rawparams.use_dngsdk = 0;
    reference.imgdata.rawparams.max_raw_memory_mb = 512;
}

static double rgb16Mean(const unsigned char* bytes, size_t size) {
    require(size > 0 && size % 2 == 0, "Invalid RGB16 bytes for mean");
    double total = 0;
    for (size_t at = 0; at < size; at += 2)
        total += unsigned(bytes[at]) | (unsigned(bytes[at + 1]) << 8);
    return total / (size / 2) / 65535.0;
}

static double officialMean(const fs::path& input, bool half, int highlight) {
    LibRaw reference;
    configureReference(reference, half, highlight);
    require(reference.open_file(input.c_str()) == 0, "Brightness reference open failed");
    require(reference.unpack() == 0, "Brightness reference unpack failed");
    require(reference.dcraw_process() == 0, "Brightness reference process failed");
    int error = 0;
    std::unique_ptr<libraw_processed_image_t, decltype(&LibRaw::dcraw_clear_mem)> pixels(
        reference.dcraw_make_mem_image(&error), LibRaw::dcraw_clear_mem);
    require(pixels && error == 0, "Brightness reference bitmap failed");
    return rgb16Mean(pixels->data, pixels->data_size);
}

static double referenceCompare(const fs::path& input, const fs::path& output, bool half) {
    std::atomic<bool> cancelled{false};
    const auto info = spektra::inspectRaw(input.string(), cancelled);
    double last = 0;
    const auto actual = spektra::developRaw(input.string(), output.string(), half, cancelled,
        [&last](const char*, double fraction) {
            require(fraction >= last, "Progress decreased"); last = fraction; return true;
        });
    LibRaw reference;
    configureReference(reference, half);
    require(reference.open_file(input.c_str()) == 0, "Reference open failed");
    require(reference.unpack() == 0, "Reference unpack failed");
    require(reference.dcraw_process() == 0, "Reference process failed");
    int error = 0;
    std::unique_ptr<libraw_processed_image_t, decltype(&LibRaw::dcraw_clear_mem)> pixels(
        reference.dcraw_make_mem_image(&error), LibRaw::dcraw_clear_mem);
    require(pixels && error == 0, "Reference bitmap failed");
    require(actual.width == pixels->width && actual.height == pixels->height, "Output dimensions differ");
    if (!half) require(info.width == actual.width && info.height == actual.height, "Info/full dimensions differ");
    const auto bytes = readBytes(output);
    require(bytes.size() == size_t(actual.width) * actual.height * 6, "RGB16LE cache byte length differs");
    require(bytes.size() == pixels->data_size, "Reference byte size differs");
    require(std::memcmp(bytes.data(), pixels->data, bytes.size()) == 0,
            "Streaming RGB16LE differs from official LibRaw memory output");
    const double mean = rgb16Mean(bytes.data(), bytes.size());
    std::cout << "PASS " << input.filename() << (half ? " half " : " full ")
              << actual.width << 'x' << actual.height << ' ' << bytes.size()
              << " bytes exact; mean=" << mean << '\n';
    return mean;
}

int main(int argc, char** argv) {
    if (argc < 2) { std::cerr << "usage: spektra_raw_validation output-dir [real-fixture.dng]\n"; return 2; }
    try {
        const fs::path dir = fs::absolute(argv[1]); fs::create_directories(dir);
        require(spektra::rawCameraSupported("Sony ILCE-7CR (A7CR)"), "Sony A7CR is not supported");
        std::cout << "LibRaw " << spektra::rawVersion() << ": Sony ILCE-7CR (A7CR) supported\n";
        for (unsigned orientation = 1; orientation <= 8; ++orientation) {
            const auto dng = dir / ("orientation-" + std::to_string(orientation) + ".dng");
            syntheticDng(dng, orientation);
            referenceCompare(dng, dir / "test.rgb16", false);
        }
        const auto valid = dir / "orientation-1.dng";
        referenceCompare(valid, dir / "test.rgb16", true);
        // The old highlight=5 policy suppressed auto-bright, and a fixed
        // gamma white in the streaming writer would independently suppress
        // it even after changing that policy. A dark RAW exposes both bugs.
        const auto dark = dir / "dark-exposure.dng";
        syntheticDng(dark, 6, 1.0 / 16);
        const double oldMean = officialMean(dark, false, 5);
        const double newMean = referenceCompare(dark, dir / "dark.rgb16", false);
        require(newMean > .35 && newMean > oldMean * 1.75,
                "Dark RAW did not receive histogram auto-brightening");
        referenceCompare(dark, dir / "dark-half.rgb16", true);
        std::cout << "PASS dark RAW auto-bright regression old_reconstruct_mean="
                  << oldMean << " blend_auto_white_mean=" << newMean << '\n';
        std::atomic<bool> cancelled{false};
        const auto cancelledOutput = dir / "cancelled.rgb16";
        fs::remove(cancelledOutput);
        bool cancelObserved = false;
        try {
            spektra::developRaw(valid.string(), cancelledOutput.string(), false, cancelled,
                [](const char*, double fraction) { return fraction < .90; });
        } catch (const spektra::RawError& error) {
            cancelObserved = error.kind == spektra::RawErrorKind::Cancelled;
        }
        require(cancelObserved && !fs::exists(cancelledOutput), "Cancellation did not clean output");
        for (const auto& entry : fs::directory_iterator(dir))
            require(entry.path().filename().string().find(".part.") == std::string::npos,
                    "Partial cache remained after cancellation");
        std::cout << "PASS cancellation removes partial RGB16LE output\n";

        { std::ofstream file(cancelledOutput); file << "previous complete cache"; }
        const auto previous = readBytes(cancelledOutput);
        cancelObserved = false;
        try {
            spektra::developRaw(valid.string(), cancelledOutput.string(), false, cancelled,
                [&cancelled](const char*, double fraction) {
                    if (fraction >= .90) cancelled.store(true);
                    return true;
                });
        } catch (const spektra::RawError& error) {
            cancelObserved = error.kind == spektra::RawErrorKind::Cancelled;
        }
        require(cancelObserved && readBytes(cancelledOutput) == previous,
                "Atomic cancellation changed a previous completed destination");
        cancelled.store(false);
        fs::remove(cancelledOutput);
        std::cout << "PASS atomic cancellation preserves completed destination\n";

        const auto invalid = dir / "unsupported.raw";
        { std::ofstream file(invalid); file << std::string(4096, 'X'); }
        bool unsupported = false;
        try { spektra::developRaw(invalid.string(), (dir / "invalid.rgb16").string(), false, cancelled); }
        catch (const spektra::RawError& error) { unsupported = error.kind == spektra::RawErrorKind::Unsupported; }
        require(unsupported && !fs::exists(dir / "invalid.rgb16"), "Unsupported input was not rejected");
        std::cout << "PASS unsupported input rejected without output\n";

        const auto truncated = dir / "truncated.dng";
        auto broken = readBytes(valid); broken.resize(broken.size() / 2);
        { std::ofstream file(truncated, std::ios::binary);
          file.write(reinterpret_cast<const char*>(broken.data()), broken.size()); }
        bool corruptRejected = false;
        try { spektra::developRaw(truncated.string(), (dir / "truncated.rgb16").string(), false, cancelled); }
        catch (const spektra::RawError& error) { corruptRejected = error.kind == spektra::RawErrorKind::Io; }
        require(corruptRejected && !fs::exists(dir / "truncated.rgb16"), "Truncated RAW was not rejected");
        std::cout << "PASS truncated RAW rejected without output\n";
        if (argc > 2) {
            referenceCompare(fs::absolute(argv[2]), dir / "real-fixture.rgb16", false);
            referenceCompare(fs::absolute(argv[2]), dir / "real-fixture-half.rgb16", true);
        }
        std::cout << "All native RAW validation checks passed\n";
    } catch (const std::exception& error) {
        std::cerr << "FAIL " << error.what() << '\n'; return 1;
    }
    return 0;
}
